"""POSTED 장부의 현금 범위를 명시적 설정으로 사전 점검합니다."""

import re
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.closing.application.service import ClosingService
from app.closing.domain.errors import ClosingRunStale
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.cash_flow.entities import (
    CashClassification,
    CashPreflight,
    CashPreflightIssue,
    CashScope,
)
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.financial_statements.domain.rules import ReportSourceStale

ZERO = Decimal("0")
ACTIVITIES = ("OPERATING", "INVESTING", "FINANCING", "EXCHANGE_EFFECT")


def covers_period(start: date, end: date | None, period_start: date, period_end: date) -> bool:
    return start <= period_start and (end is None or end >= period_end)


class CashFlowService:
    def __init__(self, factory: Callable[[], CashFlowUnitOfWork]) -> None:
        self.factory = factory

    def scopes(self, actor: Principal, company: UUID) -> tuple[CashScope, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return uow.cash_flow.scopes(company)

    def classifications(self, actor: Principal, company: UUID) -> tuple[CashClassification, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return uow.cash_flow.classifications(company)

    def map_cash(
        self,
        actor: Principal,
        company: UUID,
        account_id: UUID,
        scope_type: str,
        effective_from: date,
    ) -> CashScope:
        if scope_type not in ("CASH", "CASH_EQUIVALENT"):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            account = uow.accounts.get(company_id=company, resource_id=account_id)
            if account is None:
                raise ResourceNotFound()
            if (
                account.account_type != "ASSET"
                or account.is_contra
                or not account.posting_allowed
                or account.status != "ACTIVE"
            ):
                raise InvalidInput()
            if any(row.account_id == account_id for row in uow.cash_flow.classifications(company)):
                raise StateConflict()
            old = next(
                (row for row in uow.cash_flow.scopes(company) if row.account_id == account_id), None
            )
            if old is not None:
                if old.scope_type != scope_type or old.effective_from != effective_from:
                    raise StateConflict()
                return old
            return uow.cash_flow.add_scope(
                company, account_id, scope_type, effective_from, actor.user_id, uow.now()
            )

    def map_activity(
        self,
        actor: Principal,
        company: UUID,
        account_id: UUID,
        activity_type: str,
        line_code: str,
        effective_from: date,
    ) -> CashClassification:
        if activity_type not in ACTIVITIES or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", line_code):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            account = uow.accounts.get(company_id=company, resource_id=account_id)
            if account is None:
                raise ResourceNotFound()
            if not account.posting_allowed or account.status != "ACTIVE":
                raise InvalidInput()
            if any(row.account_id == account_id for row in uow.cash_flow.scopes(company)):
                raise StateConflict()
            old = next(
                (
                    row
                    for row in uow.cash_flow.classifications(company)
                    if row.account_id == account_id
                ),
                None,
            )
            if old is not None:
                if (
                    old.activity_type != activity_type
                    or old.line_code != line_code
                    or old.effective_from != effective_from
                ):
                    raise StateConflict()
                return old
            return uow.cash_flow.add_classification(
                company,
                account_id,
                activity_type,
                line_code,
                effective_from,
                actor.user_id,
                uow.now(),
            )

    def preflight(self, actor: Principal, company: UUID, period_id: UUID) -> CashPreflight:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            try:
                period, _, source_digest, _, facts = ClosingService.closed_adjusted_source(
                    uow, company, period_id
                )
            except ClosingRunStale:
                raise ReportSourceStale() from None
            scopes = uow.cash_flow.scopes(company)
            classes = uow.cash_flow.classifications(company)
            mapping_digest = digest(
                (
                    [
                        (str(r.account_id), r.scope_type, r.effective_from.isoformat(), r.version)
                        for r in scopes
                    ],
                    [
                        (
                            str(r.account_id),
                            r.activity_type,
                            r.line_code,
                            r.effective_from.isoformat(),
                            r.version,
                        )
                        for r in classes
                    ],
                )
            )
            issues: list[CashPreflightIssue] = []
            if not scopes:
                issues.append(CashPreflightIssue("CASH_SCOPE_MISSING"))
            cash_accounts = {row.account_id for row in scopes}
            for row in scopes:
                if not covers_period(
                    row.effective_from, row.effective_to, period.start_date, period.end_date
                ):
                    issues.append(CashPreflightIssue("CASH_SCOPE_NOT_FULL_PERIOD"))
            classes_by_account = {row.account_id: row for row in classes}
            opening = sum(
                (
                    f.debit_amount - f.credit_amount
                    for f in facts
                    if f.account_id in cash_accounts
                    and (f.entry_date < period.start_date or f.source_type == "OPENING")
                ),
                ZERO,
            )
            closing = sum(
                (f.debit_amount - f.credit_amount for f in facts if f.account_id in cash_accounts),
                ZERO,
            )
            by_journal = defaultdict(list)
            for fact in facts:
                if period.start_date <= fact.entry_date and fact.source_type != "OPENING":
                    by_journal[fact.journal_id].append(fact)
            amounts = {activity: ZERO for activity in ACTIVITIES}
            classified = 0
            for journal_id, journal_facts in by_journal.items():
                cash = [f for f in journal_facts if f.account_id in cash_accounts]
                if not cash:
                    continue
                other = [f for f in journal_facts if f.account_id not in cash_accounts]
                movement = sum((f.debit_amount - f.credit_amount for f in cash), ZERO)
                if not other and movement == ZERO:
                    continue  # 현금 계정 사이의 내부 이체는 현금흐름에서 제외합니다.
                if len(cash) != 1 or len(other) != 1:
                    issues.append(CashPreflightIssue("CASH_FLOW_COMPLEX_JOURNAL", journal_id))
                    continue
                classification = classes_by_account.get(other[0].account_id)
                if classification is None or not (
                    classification.effective_from <= other[0].entry_date
                    and (
                        classification.effective_to is None
                        or classification.effective_to >= other[0].entry_date
                    )
                ):
                    issues.append(CashPreflightIssue("CASH_FLOW_UNCLASSIFIED", journal_id))
                    continue
                amounts[classification.activity_type] += movement
                classified += 1
            net_movement = closing - opening
            if not issues and sum(amounts.values(), ZERO) != net_movement:
                issues.append(CashPreflightIssue("CASH_FLOW_RECONCILIATION_MISMATCH"))
            return CashPreflight(
                period_id=period_id,
                close_version=period.close_version,
                source_digest=source_digest,
                mapping_digest=mapping_digest,
                opening_cash=opening,
                closing_cash=closing,
                net_cash_movement=net_movement,
                net_operating=amounts["OPERATING"],
                net_investing=amounts["INVESTING"],
                net_financing=amounts["FINANCING"],
                exchange_effect=amounts["EXCHANGE_EFFECT"],
                classified_journal_count=classified,
                issues=tuple(issues),
                ready=not issues,
            )
