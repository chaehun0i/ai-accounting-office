"""Verified journal classifications and deterministic equity roll-forward."""

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from app.accounting.accounts.infrastructure.models import AccountModel
from app.accounting.journals.infrastructure.models import (
    JournalEvidenceModel,
    JournalLineModel,
    JournalModel,
)
from app.closing.application.service import ClosingService
from app.closing.domain.errors import ClosingRunStale
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.contracts.errors import ApplicationError
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.cash_flow.snapshot_models import CashFlowEventModel, CashFlowStatementModel
from app.reporting.equity.models import (
    DividendDeclarationModel,
    DividendPaymentModel,
    EquityAccountMappingModel,
    EquityCommandModel,
    EquityComponentModel,
    EquityEventModel,
    EquityStatementLineModel,
    EquityStatementModel,
    EquityStatementSourceModel,
)
from app.reporting.financial_statements.domain.rules import ReportSourceStale
from app.reporting.financial_statements.infrastructure.unit_of_work import (
    ReportingSQLAlchemyUnitOfWork,
)

ZERO = Decimal("0")
TYPES = {
    "CONTRIBUTED_CAPITAL",
    "RETAINED_EARNINGS",
    "TREASURY_STOCK",
    "OTHER_EQUITY",
    "OCI_COMPONENT",
}
EVENT_TYPES = {
    "CAPITAL_CONTRIBUTION",
    "CAPITAL_REDUCTION",
    "DIVIDEND",
    "TREASURY_STOCK_ACQUIRE",
    "TREASURY_STOCK_DISPOSE",
    "PROFIT_TRANSFER",
    "OCI_TRANSFER",
    "OTHER_ADJUSTMENT",
}
OWNER_TYPES = {
    "CAPITAL_CONTRIBUTION",
    "CAPITAL_REDUCTION",
    "DIVIDEND",
    "TREASURY_STOCK_ACQUIRE",
    "TREASURY_STOCK_DISPOSE",
}
MOVEMENTS = (
    "OPENING",
    "OWNER_TRANSACTIONS",
    "PROFIT_OR_LOSS",
    "OTHER_COMPREHENSIVE_INCOME",
    "OTHER_ADJUSTMENTS",
    "CLOSING",
)


class EquityRollforwardMismatch(ApplicationError):
    code = "EQUITY_ROLLFORWARD_MISMATCH"
    status_code = 422
    message = "자본변동 원천과 재무제표 잔액이 일치하지 않습니다."


@dataclass(frozen=True)
class EquityReadiness:
    period_id: UUID
    status: str
    issues: tuple[str, ...]
    balance_sheet_equity: Decimal | None
    income_statement_profit: Decimal | None
    rollforward_equity: Decimal | None
    source_digest: str | None


def _row(row: object) -> dict[str, object]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}  # type: ignore[attr-defined]


class EquityService:
    def __init__(self, factory: Callable[[], ReportingSQLAlchemyUnitOfWork]) -> None:
        self.factory = factory

    def components(self, actor: Principal, company: UUID) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return [
                _row(row)
                for row in uow.session.scalars(
                    select(EquityComponentModel)
                    .where(EquityComponentModel.company_id == company)
                    .order_by(
                        EquityComponentModel.display_order, EquityComponentModel.component_code
                    )
                )
            ]

    def add_component(
        self,
        actor: Principal,
        company: UUID,
        code: str,
        name: str,
        component_type: str,
        display_order: int,
    ) -> dict[str, object]:
        if (
            not re.fullmatch(r"[A-Z][A-Z0-9_]{1,39}", code)
            or not name.strip()
            or component_type not in TYPES
            or display_order < 1
        ):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            existing = uow.session.scalar(
                select(EquityComponentModel).where(
                    EquityComponentModel.company_id == company,
                    EquityComponentModel.component_code == code,
                )
            )
            if existing:
                if (existing.name, existing.component_type, existing.display_order) != (
                    name.strip(),
                    component_type,
                    display_order,
                ):
                    raise StateConflict()
                return _row(existing)
            row = EquityComponentModel(
                id=uuid4(),
                company_id=company,
                component_code=code,
                name=name.strip(),
                component_type=component_type,
                status="ACTIVE",
                display_order=display_order,
                version=1,
                created_by=actor.user_id,
                created_at=uow.now(),
            )
            uow.session.add(row)
            uow.session.flush()
            return _row(row)

    def mappings(self, actor: Principal, company: UUID) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return [
                _row(row)
                for row in uow.session.scalars(
                    select(EquityAccountMappingModel)
                    .where(EquityAccountMappingModel.company_id == company)
                    .order_by(
                        EquityAccountMappingModel.account_id, EquityAccountMappingModel.version
                    )
                )
            ]

    def map_account(
        self,
        actor: Principal,
        company: UUID,
        component_id: UUID,
        account_id: UUID,
        effective_from: date,
    ) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            component = uow.session.scalar(
                select(EquityComponentModel).where(
                    EquityComponentModel.company_id == company,
                    EquityComponentModel.id == component_id,
                )
            )
            account = uow.accounts.get(company_id=company, resource_id=account_id)
            if component is None or account is None:
                raise ResourceNotFound()
            if (
                component.status != "ACTIVE"
                or account.account_type != "EQUITY"
                or not account.posting_allowed
            ):
                raise InvalidInput()
            previous = uow.session.scalar(
                select(EquityAccountMappingModel)
                .where(
                    EquityAccountMappingModel.company_id == company,
                    EquityAccountMappingModel.account_id == account_id,
                    EquityAccountMappingModel.status == "ACTIVE",
                )
                .order_by(EquityAccountMappingModel.version.desc())
                .limit(1)
            )
            if previous:
                if (
                    previous.component_id == component_id
                    and previous.effective_from == effective_from
                ):
                    return _row(previous)
                raise StateConflict()
            row = EquityAccountMappingModel(
                id=uuid4(),
                company_id=company,
                component_id=component_id,
                account_id=account_id,
                effective_from=effective_from,
                effective_to=None,
                status="ACTIVE",
                version=1,
                created_by=actor.user_id,
                created_at=uow.now(),
            )
            uow.session.add(row)
            uow.session.flush()
            return _row(row)

    def events(self, actor: Principal, company: UUID, period_id: UUID) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            period = uow.periods.get(company_id=company, resource_id=period_id)
            if period is None:
                raise ResourceNotFound()
            return [
                _row(row)
                for row in uow.session.scalars(
                    select(EquityEventModel)
                    .where(
                        EquityEventModel.company_id == company,
                        EquityEventModel.event_date >= period.start_date,
                        EquityEventModel.event_date <= period.end_date,
                    )
                    .order_by(EquityEventModel.event_date, EquityEventModel.id)
                )
            ]

    def classify_event(
        self,
        actor: Principal,
        company: UUID,
        journal_line_id: UUID,
        event_type: str,
    ) -> dict[str, object]:
        if event_type not in EVENT_TYPES:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            record = uow.session.execute(
                select(JournalLineModel, JournalModel, AccountModel)
                .join(
                    JournalModel,
                    (JournalModel.company_id == company)
                    & (JournalModel.id == JournalLineModel.journal_entry_id),
                )
                .join(
                    AccountModel,
                    (AccountModel.company_id == company)
                    & (AccountModel.id == JournalLineModel.account_id),
                )
                .where(
                    JournalLineModel.company_id == company, JournalLineModel.id == journal_line_id
                )
            ).first()
            if record is None:
                raise ResourceNotFound()
            line, journal, account = record
            if (
                journal.status != "POSTED"
                or journal.source_type == "OPENING"
                or journal.approval_id is None
                or account.account_type != "EQUITY"
            ):
                raise StateConflict()
            existing = uow.session.scalar(
                select(EquityEventModel).where(
                    EquityEventModel.company_id == company,
                    EquityEventModel.source_journal_line_id == journal_line_id,
                )
            )
            if existing:
                if existing.event_type != event_type:
                    raise StateConflict()
                return _row(existing)
            mapping = uow.session.scalar(
                select(EquityAccountMappingModel).where(
                    EquityAccountMappingModel.company_id == company,
                    EquityAccountMappingModel.account_id == account.id,
                    EquityAccountMappingModel.status == "ACTIVE",
                    EquityAccountMappingModel.effective_from <= journal.entry_date,
                    (EquityAccountMappingModel.effective_to.is_(None))
                    | (EquityAccountMappingModel.effective_to >= journal.entry_date),
                )
            )
            if mapping is None:
                raise StateConflict()
            component = uow.session.scalar(
                select(EquityComponentModel).where(
                    EquityComponentModel.company_id == company,
                    EquityComponentModel.id == mapping.component_id,
                )
            )
            assert component is not None
            required_type = (
                "CONTRIBUTED_CAPITAL"
                if event_type.startswith("CAPITAL_")
                else "TREASURY_STOCK"
                if event_type.startswith("TREASURY_STOCK_")
                else "RETAINED_EARNINGS"
                if event_type in {"DIVIDEND", "PROFIT_TRANSFER"}
                else "OCI_COMPONENT"
                if event_type == "OCI_TRANSFER"
                else None
            )
            if required_type and component.component_type != required_type:
                raise InvalidInput()
            amount = line.credit_amount - line.debit_amount
            if event_type in {"CAPITAL_CONTRIBUTION", "TREASURY_STOCK_DISPOSE"} and amount <= ZERO:
                raise InvalidInput()
            if (
                event_type in {"CAPITAL_REDUCTION", "DIVIDEND", "TREASURY_STOCK_ACQUIRE"}
                and amount >= ZERO
            ):
                raise InvalidInput()
            if event_type == "DIVIDEND":
                declaration = uow.session.scalar(
                    select(DividendDeclarationModel).where(
                        DividendDeclarationModel.company_id == company,
                        DividendDeclarationModel.source_journal_id == journal.id,
                        DividendDeclarationModel.status == "APPROVED",
                    )
                )
                if declaration is None or declaration.total_amount != -amount:
                    raise StateConflict()
            row = EquityEventModel(
                id=uuid4(),
                company_id=company,
                component_id=mapping.component_id,
                event_date=journal.entry_date,
                event_type=event_type,
                amount=amount,
                source_journal_id=journal.id,
                source_journal_line_id=line.id,
                approval_id=journal.approval_id,
                mapping_version=mapping.version,
                status="VERIFIED",
                created_by=actor.user_id,
                created_at=uow.now(),
            )
            uow.session.add(row)
            uow.session.flush()
            return _row(row)

    def declarations(self, actor: Principal, company: UUID) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return [
                _row(row)
                for row in uow.session.scalars(
                    select(DividendDeclarationModel)
                    .where(DividendDeclarationModel.company_id == company)
                    .order_by(DividendDeclarationModel.resolution_date, DividendDeclarationModel.id)
                )
            ]

    def payments(
        self, actor: Principal, company: UUID, declaration_id: UUID
    ) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            declaration = uow.session.scalar(
                select(DividendDeclarationModel).where(
                    DividendDeclarationModel.company_id == company,
                    DividendDeclarationModel.id == declaration_id,
                )
            )
            if declaration is None:
                raise ResourceNotFound()
            return [
                _row(row)
                for row in uow.session.scalars(
                    select(DividendPaymentModel)
                    .where(
                        DividendPaymentModel.company_id == company,
                        DividendPaymentModel.declaration_id == declaration_id,
                    )
                    .order_by(DividendPaymentModel.payment_date, DividendPaymentModel.id)
                )
            ]

    def record_payment(
        self,
        actor: Principal,
        company: UUID,
        declaration_id: UUID,
        cash_flow_event_id: UUID,
    ) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            declaration = uow.session.scalar(
                select(DividendDeclarationModel)
                .where(
                    DividendDeclarationModel.company_id == company,
                    DividendDeclarationModel.id == declaration_id,
                )
                .with_for_update()
            )
            event = uow.session.scalar(
                select(CashFlowEventModel).where(
                    CashFlowEventModel.company_id == company,
                    CashFlowEventModel.id == cash_flow_event_id,
                )
            )
            if declaration is None or event is None:
                raise ResourceNotFound()
            if declaration.status != "APPROVED" or declaration.source_journal_id is None:
                raise StateConflict()
            existing = uow.session.scalar(
                select(DividendPaymentModel).where(
                    DividendPaymentModel.company_id == company,
                    DividendPaymentModel.cash_flow_event_id == cash_flow_event_id,
                )
            )
            if existing:
                if existing.declaration_id != declaration_id:
                    raise StateConflict()
                return _row(existing)
            statement = uow.session.scalar(
                select(CashFlowStatementModel).where(
                    CashFlowStatementModel.company_id == company,
                    CashFlowStatementModel.id == event.statement_id,
                )
            )
            journal = uow.journals.get(company, event.journal_id)
            if (
                statement is None
                or statement.status != "RECONCILED"
                or journal is None
                or journal.status != "POSTED"
                or event.activity_type != "FINANCING"
                or event.cash_outflow <= ZERO
            ):
                raise StateConflict()
            declaration_accounts = set(
                uow.session.scalars(
                    select(JournalLineModel.account_id).where(
                        JournalLineModel.company_id == company,
                        JournalLineModel.journal_entry_id == declaration.source_journal_id,
                        JournalLineModel.credit_amount > ZERO,
                    )
                )
            )
            if event.counterpart_account_id not in declaration_accounts:
                raise StateConflict()
            payments = list(
                uow.session.scalars(
                    select(DividendPaymentModel).where(
                        DividendPaymentModel.company_id == company,
                        DividendPaymentModel.declaration_id == declaration_id,
                    )
                )
            )
            if (
                sum((p.amount for p in payments), ZERO) + event.cash_outflow
                > declaration.total_amount
            ):
                raise StateConflict()
            row = DividendPaymentModel(
                id=uuid4(),
                company_id=company,
                declaration_id=declaration_id,
                cash_flow_statement_id=statement.id,
                cash_flow_event_id=event.id,
                journal_id=journal.id,
                payment_date=journal.entry_date,
                amount=event.cash_outflow,
                created_by=actor.user_id,
                created_at=uow.now(),
            )
            uow.session.add(row)
            uow.session.flush()
            return _row(row)

    def declare_dividend(
        self,
        actor: Principal,
        company: UUID,
        resolution_date: date,
        payable_date: date | None,
        total_amount: Decimal,
        source_journal_id: UUID | None,
    ) -> dict[str, object]:
        if total_amount <= ZERO or (payable_date and payable_date < resolution_date):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            journal = None
            if source_journal_id:
                journal = uow.journals.get(company, source_journal_id)
                if journal is None:
                    raise ResourceNotFound()
                if journal.status != "POSTED" or journal.approval_id is None:
                    raise StateConflict()
                if resolution_date > journal.entry_date:
                    raise InvalidInput()
                retained_accounts = set(
                    uow.session.scalars(
                        select(EquityAccountMappingModel.account_id)
                        .join(
                            EquityComponentModel,
                            (EquityComponentModel.company_id == company)
                            & (EquityComponentModel.id == EquityAccountMappingModel.component_id),
                        )
                        .where(
                            EquityAccountMappingModel.company_id == company,
                            EquityAccountMappingModel.status == "ACTIVE",
                            EquityComponentModel.component_type == "RETAINED_EARNINGS",
                        )
                    )
                )
                debit = sum(
                    (
                        line.debit_amount
                        for line in uow.session.scalars(
                            select(JournalLineModel).where(
                                JournalLineModel.company_id == company,
                                JournalLineModel.journal_entry_id == journal.id,
                                JournalLineModel.account_id.in_(retained_accounts),
                            )
                        )
                    ),
                    ZERO,
                )
                if debit != total_amount:
                    raise StateConflict()
            row = DividendDeclarationModel(
                id=uuid4(),
                company_id=company,
                resolution_date=resolution_date,
                payable_date=payable_date,
                total_amount=total_amount,
                status="APPROVED" if journal else "PROPOSED",
                approval_id=journal.approval_id if journal else None,
                source_journal_id=journal.id if journal else None,
                created_by=actor.user_id,
                created_at=uow.now(),
            )
            uow.session.add(row)
            uow.session.flush()
            return _row(row)

    def _calculate(
        self, uow: ReportingSQLAlchemyUnitOfWork, company: UUID, period_id: UUID
    ) -> tuple[Any, ...]:
        issues: list[str] = []
        try:
            period, _, source_digest, _, facts = ClosingService.closed_adjusted_source(
                uow, company, period_id
            )
        except ClosingRunStale:
            raise ReportSourceStale() from None
        statement_set = next(
            (
                item
                for item in uow.statements.sets(company, period_id)
                if item.close_version == period.close_version
                and item.trial_balance_digest == source_digest
            ),
            None,
        )
        if statement_set is None:
            issues.append("BS_IS_SNAPSHOT_MISSING")
            return period, None, None, None, {}, {}, facts, source_digest, "", "", issues
        balance = uow.statements.statement(company, statement_set.id, "BALANCE_SHEET")
        income = uow.statements.statement(company, statement_set.id, "INCOME_STATEMENT")
        if balance is None or income is None:
            issues.append("BS_IS_SNAPSHOT_MISSING")
            return (
                period,
                statement_set,
                balance,
                income,
                {},
                {},
                facts,
                source_digest,
                "",
                "",
                issues,
            )
        bs_equity = next(
            line.current_amount for line in balance.lines if line.line_code == "EQUITY"
        )
        net_profit = next(
            line.current_amount for line in income.lines if line.line_code == "NET_PROFIT"
        )
        components = list(
            uow.session.scalars(
                select(EquityComponentModel)
                .where(
                    EquityComponentModel.company_id == company,
                    EquityComponentModel.status == "ACTIVE",
                )
                .order_by(EquityComponentModel.display_order, EquityComponentModel.id)
            )
        )
        mappings = list(
            uow.session.scalars(
                select(EquityAccountMappingModel).where(
                    EquityAccountMappingModel.company_id == company,
                    EquityAccountMappingModel.status == "ACTIVE",
                    EquityAccountMappingModel.effective_from <= period.start_date,
                    (EquityAccountMappingModel.effective_to.is_(None))
                    | (EquityAccountMappingModel.effective_to >= period.end_date),
                )
            )
        )
        mapped: dict[UUID, EquityAccountMappingModel] = {}
        for mapping in mappings:
            if mapping.account_id in mapped:
                issues.append("DUPLICATE_EQUITY_MAPPING")
            mapped[mapping.account_id] = mapping
        active_ids = {component.id for component in components}
        if any(mapping.component_id not in active_ids for mapping in mappings):
            issues.append("INACTIVE_EQUITY_COMPONENT")
        account_types = {
            account.id: account.account_type
            for account in uow.session.scalars(
                select(AccountModel).where(AccountModel.company_id == company)
            )
        }
        current_equity_facts = [fact for fact in facts if fact.account_id in mapped]
        if any(
            fact.account_id not in mapped
            for fact in facts
            if account_types.get(fact.account_id) == "EQUITY"
        ):
            issues.append("EQUITY_MAPPING_INCOMPLETE")
        events = list(
            uow.session.scalars(
                select(EquityEventModel).where(
                    EquityEventModel.company_id == company,
                    EquityEventModel.event_date >= period.start_date,
                    EquityEventModel.event_date <= period.end_date,
                )
            )
        )
        by_line = {event.source_journal_line_id: event for event in events}
        for fact in current_equity_facts:
            if fact.entry_date < period.start_date or fact.source_type == "OPENING":
                continue
            event = by_line.get(fact.line_id)
            if (
                event is None
                or event.component_id != mapped[fact.account_id].component_id
                or event.mapping_version != mapped[fact.account_id].version
                or event.amount != fact.credit_amount - fact.debit_amount
            ):
                issues.append("UNCLASSIFIED_EQUITY_SOURCE")
        if not components:
            issues.append("EQUITY_COMPONENT_MISSING")
        prior_period = next(
            (
                item
                for item in reversed(uow.periods.list(company))
                if item.end_date == period.start_date - timedelta(days=1)
            ),
            None,
        )
        prior_equity: Decimal | None = None
        prior_digest: str | None = None
        if prior_period is not None and prior_period.status == "CLOSED":
            try:
                _, _, prior_source_digest, _, _ = ClosingService.closed_adjusted_source(
                    uow, company, prior_period.id
                )
            except ClosingRunStale:
                prior_source_digest = None
                issues.append("PRIOR_EQUITY_SNAPSHOT_STALE")
            prior_set = next(
                (
                    item
                    for item in uow.statements.sets(company, prior_period.id)
                    if item.close_version == prior_period.close_version
                    and item.trial_balance_digest == prior_source_digest
                ),
                None,
            )
            if prior_set:
                prior_balance = uow.statements.statement(company, prior_set.id, "BALANCE_SHEET")
                if prior_balance:
                    prior_digest = prior_balance.snapshot_digest
                    prior_equity = next(
                        line.current_amount
                        for line in prior_balance.lines
                        if line.line_code == "EQUITY"
                    )
        if prior_period is not None and prior_equity is None:
            issues.append("PRIOR_EQUITY_SNAPSHOT_MISSING")
        if prior_period is None and not any(fact.source_type == "OPENING" for fact in facts):
            issues.append("OPENING_EQUITY_UNVERIFIED")
        transfer_journals = {
            event.source_journal_id for event in events if event.event_type == "PROFIT_TRANSFER"
        }
        if transfer_journals:
            operational_profit = sum(
                (
                    fact.credit_amount - fact.debit_amount
                    for fact in facts
                    if period.start_date <= fact.entry_date <= period.end_date
                    and fact.journal_id not in transfer_journals
                    and account_types.get(fact.account_id) in {"REVENUE", "EXPENSE"}
                ),
                ZERO,
            )
            if operational_profit != net_profit:
                issues.append("PROFIT_TRANSFER_IS_MISMATCH")
            for journal_id in transfer_journals:
                journal_facts = [fact for fact in facts if fact.journal_id == journal_id]
                transfer_events = [
                    event
                    for event in events
                    if event.event_type == "PROFIT_TRANSFER"
                    and event.source_journal_id == journal_id
                ]
                transferred_profit = sum(
                    (
                        fact.credit_amount - fact.debit_amount
                        for fact in journal_facts
                        if account_types.get(fact.account_id) in {"REVENUE", "EXPENSE"}
                    ),
                    ZERO,
                )
                retained_transfer = sum(
                    (event.amount for event in transfer_events),
                    ZERO,
                )
                if (
                    not journal_facts
                    or len(transfer_events) != 1
                    or transferred_profit + retained_transfer != ZERO
                    or any(
                        account_types.get(fact.account_id) not in {"REVENUE", "EXPENSE", "EQUITY"}
                        for fact in journal_facts
                    )
                ):
                    issues.append("PROFIT_TRANSFER_SOURCE_MISMATCH")
        amounts = {
            component.id: {movement: ZERO for movement in MOVEMENTS} for component in components
        }
        sources: dict[tuple[UUID, str], list[tuple[UUID | None, UUID | None, Decimal]]] = (
            defaultdict(list)
        )
        for fact in current_equity_facts:
            component_id = mapped[fact.account_id].component_id
            if component_id not in amounts:
                continue
            amount = fact.credit_amount - fact.debit_amount
            if fact.entry_date < period.start_date or fact.source_type == "OPENING":
                movement = "OPENING"
            else:
                event = by_line.get(fact.line_id)
                if event is None:
                    continue
                if event.event_type == "PROFIT_TRANSFER":
                    # 이미 기초 미대체 손익에 포함된 금액의 물리적 계정 대체다.
                    # 이동 원천은 보존하되 총자본 변동으로 다시 더하지 않는다.
                    sources[(component_id, "OTHER_ADJUSTMENTS")].append(
                        (fact.line_id, None, amount)
                    )
                    for transfer_fact in facts:
                        if transfer_fact.journal_id == fact.journal_id and account_types.get(
                            transfer_fact.account_id
                        ) in {"REVENUE", "EXPENSE"}:
                            sources[(component_id, "OTHER_ADJUSTMENTS")].append(
                                (
                                    transfer_fact.line_id,
                                    None,
                                    transfer_fact.credit_amount - transfer_fact.debit_amount,
                                )
                            )
                    continue
                movement = (
                    "OWNER_TRANSACTIONS"
                    if event.event_type in OWNER_TYPES
                    else "OTHER_COMPREHENSIVE_INCOME"
                    if event.event_type == "OCI_TRANSFER"
                    else "OTHER_ADJUSTMENTS"
                )
            amounts[component_id][movement] += amount
            sources[(component_id, movement)].append((fact.line_id, None, amount))
        retained = [
            component for component in components if component.component_type == "RETAINED_EARNINGS"
        ]
        if len(retained) != 1:
            issues.append("RETAINED_EARNINGS_COMPONENT_REQUIRED")
        else:
            retained_id = retained[0].id
            prior_profit = ZERO
            for fact in facts:
                if fact.entry_date < period.start_date and account_types.get(fact.account_id) in {
                    "REVENUE",
                    "EXPENSE",
                }:
                    amount = fact.credit_amount - fact.debit_amount
                    prior_profit += amount
                    sources[(retained_id, "OPENING")].append((fact.line_id, None, amount))
            amounts[retained_id]["OPENING"] += prior_profit
            amounts[retained_id]["PROFIT_OR_LOSS"] = net_profit
            sources[(retained_id, "PROFIT_OR_LOSS")].append((None, income.id, net_profit))
        for values in amounts.values():
            values["CLOSING"] = sum((values[m] for m in MOVEMENTS if m != "CLOSING"), ZERO)
        rollforward = sum((values["CLOSING"] for values in amounts.values()), ZERO)
        opening_equity = sum((values["OPENING"] for values in amounts.values()), ZERO)
        if prior_equity is not None and prior_equity != opening_equity:
            issues.append("PRIOR_EQUITY_MISMATCH")
        if rollforward != bs_equity:
            issues.append("EQUITY_ROLLFORWARD_MISMATCH")
        event_digest = digest(
            [
                (str(e.id), e.event_type, str(e.amount), str(e.source_journal_line_id))
                for e in sorted(events, key=lambda e: str(e.id))
            ]
        )
        mapping_digest = digest(
            [
                (str(m.account_id), str(m.component_id), m.version)
                for m in sorted(mappings, key=lambda m: str(m.account_id))
            ]
        )
        payments = list(
            uow.session.scalars(
                select(DividendPaymentModel)
                .where(
                    DividendPaymentModel.company_id == company,
                    DividendPaymentModel.payment_date >= period.start_date,
                    DividendPaymentModel.payment_date <= period.end_date,
                )
                .order_by(DividendPaymentModel.id)
            )
        )
        payment_identity: list[tuple[str, str, str]] = []
        for payment in payments:
            cash_statement = uow.session.scalar(
                select(CashFlowStatementModel).where(
                    CashFlowStatementModel.company_id == company,
                    CashFlowStatementModel.id == payment.cash_flow_statement_id,
                )
            )
            cash_event = uow.session.scalar(
                select(CashFlowEventModel).where(
                    CashFlowEventModel.company_id == company,
                    CashFlowEventModel.id == payment.cash_flow_event_id,
                )
            )
            if (
                cash_statement is None
                or cash_event is None
                or cash_statement.period_id != period_id
                or cash_statement.statement_set_id != statement_set.id
                or cash_statement.balance_sheet_digest != balance.snapshot_digest
                or cash_statement.income_statement_digest != income.snapshot_digest
                or cash_event.statement_id != cash_statement.id
                or cash_event.activity_type != "FINANCING"
                or cash_event.cash_outflow != payment.amount
            ):
                issues.append("DIVIDEND_CF_SOURCE_MISMATCH")
            else:
                payment_identity.append(
                    (str(payment.id), str(payment.amount), cash_statement.snapshot_digest)
                )
        identity = digest(
            (
                str(statement_set.id),
                balance.snapshot_digest,
                income.snapshot_digest,
                source_digest,
                mapping_digest,
                event_digest,
                prior_digest,
                payment_identity,
                [
                    (str(cid), [(m, str(v)) for m, v in values.items()])
                    for cid, values in amounts.items()
                ],
            )
        )
        return (
            period,
            statement_set,
            balance,
            income,
            amounts,
            sources,
            facts,
            identity,
            mapping_digest,
            event_digest,
            list(dict.fromkeys(issues)),
        )

    def reconciliation(self, actor: Principal, company: UUID, period_id: UUID) -> EquityReadiness:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            result = self._calculate(uow, company, period_id)
            _, _, balance, income, amounts, _, _, identity, _, _, issues = result
            return EquityReadiness(
                period_id,
                "BLOCKED" if issues else "READY",
                tuple(issues),
                next(
                    (line.current_amount for line in balance.lines if line.line_code == "EQUITY"),
                    None,
                )
                if balance
                else None,
                next(
                    (
                        line.current_amount
                        for line in income.lines
                        if line.line_code == "NET_PROFIT"
                    ),
                    None,
                )
                if income
                else None,
                sum((v["CLOSING"] for v in amounts.values()), ZERO) if amounts else None,
                identity,
            )

    def generate(
        self, actor: Principal, company: UUID, period_id: UUID, key: str
    ) -> dict[str, object]:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            (
                period,
                statement_set,
                balance,
                income,
                amounts,
                sources,
                _,
                identity,
                mapping_digest,
                event_digest,
                issues,
            ) = self._calculate(uow, company, period_id)
            if issues or statement_set is None or balance is None or income is None:
                raise EquityRollforwardMismatch()
            uow.lock_command(company, actor.user_id, "equity.generate", key)
            fingerprint = digest((str(period_id), identity))
            command = uow.session.scalar(
                select(EquityCommandModel).where(
                    EquityCommandModel.company_id == company,
                    EquityCommandModel.actor_id == actor.user_id,
                    EquityCommandModel.idempotency_key == key,
                )
            )
            if command:
                if command.fingerprint != fingerprint:
                    raise StateConflict()
                replay = uow.session.scalar(
                    select(EquityStatementModel).where(
                        EquityStatementModel.company_id == company,
                        EquityStatementModel.id == command.statement_id,
                    )
                )
                assert replay is not None
                return _row(replay)
            existing = uow.session.scalar(
                select(EquityStatementModel).where(
                    EquityStatementModel.company_id == company,
                    EquityStatementModel.period_id == period_id,
                    EquityStatementModel.snapshot_digest == identity,
                )
            )
            if existing:
                uow.session.add(
                    EquityCommandModel(
                        id=uuid4(),
                        company_id=company,
                        actor_id=actor.user_id,
                        idempotency_key=key,
                        fingerprint=fingerprint,
                        statement_id=existing.id,
                        created_at=uow.now(),
                    )
                )
                return _row(existing)
            now = uow.now()
            components = list(
                uow.session.scalars(
                    select(EquityComponentModel)
                    .where(
                        EquityComponentModel.company_id == company,
                        EquityComponentModel.id.in_(amounts),
                    )
                    .order_by(EquityComponentModel.display_order)
                )
            )
            row = EquityStatementModel(
                id=uuid4(),
                company_id=company,
                statement_set_id=statement_set.id,
                period_id=period_id,
                close_version=period.close_version,
                balance_sheet_digest=balance.snapshot_digest,
                income_statement_digest=income.snapshot_digest,
                mapping_digest=mapping_digest,
                event_digest=event_digest,
                source_digest=statement_set.trial_balance_digest,
                snapshot_digest=identity,
                status="RECONCILED",
                generated_by=actor.user_id,
                generated_at=now,
            )
            uow.session.add(row)
            uow.session.flush()
            for component in components:
                for order, movement in enumerate(MOVEMENTS, 1):
                    line = EquityStatementLineModel(
                        id=uuid4(),
                        company_id=company,
                        statement_id=row.id,
                        component_id=component.id,
                        movement_type=movement,
                        amount=amounts[component.id][movement],
                        display_order=order,
                    )
                    uow.session.add(line)
                    uow.session.flush()
                    for journal_line_id, income_id, amount in sources.get(
                        (component.id, movement), []
                    ):
                        uow.session.add(
                            EquityStatementSourceModel(
                                id=uuid4(),
                                company_id=company,
                                statement_line_id=line.id,
                                journal_line_id=journal_line_id,
                                income_statement_id=income_id,
                                amount=amount,
                            )
                        )
            uow.session.add(
                EquityCommandModel(
                    id=uuid4(),
                    company_id=company,
                    actor_id=actor.user_id,
                    idempotency_key=key,
                    fingerprint=fingerprint,
                    statement_id=row.id,
                    created_at=now,
                )
            )
            return _row(row)

    def snapshots(
        self, actor: Principal, company: UUID, period_id: UUID
    ) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            if uow.periods.get(company_id=company, resource_id=period_id) is None:
                raise ResourceNotFound()
            return [
                _row(row)
                for row in uow.session.scalars(
                    select(EquityStatementModel)
                    .where(
                        EquityStatementModel.company_id == company,
                        EquityStatementModel.period_id == period_id,
                    )
                    .order_by(EquityStatementModel.generated_at.desc(), EquityStatementModel.id)
                )
            ]

    def snapshot(self, actor: Principal, company: UUID, snapshot_id: UUID) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            row = uow.session.scalar(
                select(EquityStatementModel).where(
                    EquityStatementModel.company_id == company,
                    EquityStatementModel.id == snapshot_id,
                )
            )
            if row is None:
                raise ResourceNotFound()
            lines = list(
                uow.session.scalars(
                    select(EquityStatementLineModel)
                    .where(
                        EquityStatementLineModel.company_id == company,
                        EquityStatementLineModel.statement_id == snapshot_id,
                    )
                    .order_by(
                        EquityStatementLineModel.display_order,
                        EquityStatementLineModel.component_id,
                    )
                )
            )
            return {**_row(row), "lines": [_row(line) for line in lines]}

    def drilldown(
        self,
        actor: Principal,
        company: UUID,
        snapshot_id: UUID,
        line_id: UUID,
    ) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            line = uow.session.scalar(
                select(EquityStatementLineModel).where(
                    EquityStatementLineModel.company_id == company,
                    EquityStatementLineModel.statement_id == snapshot_id,
                    EquityStatementLineModel.id == line_id,
                )
            )
            if line is None:
                raise ResourceNotFound()
            result: list[dict[str, object]] = []
            for source in uow.session.scalars(
                select(EquityStatementSourceModel).where(
                    EquityStatementSourceModel.company_id == company,
                    EquityStatementSourceModel.statement_line_id == line_id,
                )
            ):
                journal_id = None
                account_code = None
                account_name = None
                journal_no = None
                entry_date = None
                evidence_ids: list[UUID] = []
                if source.journal_line_id:
                    journal_line = uow.session.scalar(
                        select(JournalLineModel).where(
                            JournalLineModel.company_id == company,
                            JournalLineModel.id == source.journal_line_id,
                        )
                    )
                    journal_id = journal_line.journal_entry_id if journal_line else None
                    if journal_line:
                        account = uow.session.scalar(
                            select(AccountModel).where(
                                AccountModel.company_id == company,
                                AccountModel.id == journal_line.account_id,
                            )
                        )
                        journal = uow.session.scalar(
                            select(JournalModel).where(
                                JournalModel.company_id == company,
                                JournalModel.id == journal_id,
                            )
                        )
                        if account and journal:
                            account_code = account.account_code
                            account_name = account.account_name
                            journal_no = journal.journal_no
                            entry_date = journal.entry_date
                            evidence_ids = list(
                                uow.session.scalars(
                                    select(JournalEvidenceModel.evidence_id).where(
                                        JournalEvidenceModel.company_id == company,
                                        JournalEvidenceModel.journal_entry_id == journal.id,
                                    )
                                )
                            )
                result.append(
                    {
                        "journal_id": journal_id,
                        "journal_line_id": source.journal_line_id,
                        "journal_no": journal_no,
                        "entry_date": entry_date,
                        "account_code": account_code,
                        "account_name": account_name,
                        "evidence_ids": evidence_ids,
                        "income_statement_id": source.income_statement_id,
                        "amount": source.amount,
                    }
                )
            return result
