"""Deterministic disclosure facts pinned to the current closed statement set."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from app.accounting.accounts.infrastructure.models import AccountModel
from app.accounting.journals.infrastructure.models import JournalEvidenceModel
from app.accounting.periods.infrastructure.models import PeriodModel
from app.closing.domain.errors import ClosingRunStale
from app.companies.application.service import require_company
from app.contracts.access_errors import (
    DisclosureStale,
    InvalidInput,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.cash_flow.service import CashFlowService
from app.reporting.cash_flow.snapshot_models import (
    CashFlowAdjustmentSourceModel,
    CashFlowEventModel,
    CashFlowLineModel,
    CashFlowStatementModel,
)
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.disclosures.models import (
    DisclosureAuditModel,
    DisclosureCommandModel,
    DisclosureFieldModel,
    DisclosureInstanceModel,
    DisclosureNarrativeModel,
    DisclosureSectionModel,
    DisclosureTemplateModel,
    DisclosureValueModel,
)
from app.reporting.equity.models import (
    EquityComponentModel,
    EquityStatementLineModel,
    EquityStatementModel,
)
from app.reporting.equity.service import EquityService
from app.reporting.financial_statements.domain.rules import ReportSourceStale
from app.reporting.financial_statements.infrastructure.models import StatementSourceModel

TEMPLATE_CODE = "INTERNAL_CORE_NOTES"


def _serialize(row: object) -> dict[str, object]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}  # type: ignore[attr-defined]


class DisclosureService:
    def __init__(self, factory: Callable[[], CashFlowUnitOfWork]) -> None:
        self.factory = factory

    def _template(
        self, uow: CashFlowUnitOfWork, period_start: date, period_end: date
    ) -> tuple[
        DisclosureTemplateModel,
        dict[tuple[str, str], tuple[DisclosureSectionModel, DisclosureFieldModel]],
    ]:
        template = uow.session.scalar(
            select(DisclosureTemplateModel).where(
                DisclosureTemplateModel.framework_code == "INTERNAL",
                DisclosureTemplateModel.template_code == TEMPLATE_CODE,
                DisclosureTemplateModel.version == 1,
                DisclosureTemplateModel.status == "ACTIVE",
                DisclosureTemplateModel.effective_from <= period_end,
                (DisclosureTemplateModel.effective_to.is_(None))
                | (DisclosureTemplateModel.effective_to >= period_start),
            )
        )
        if template is None:
            raise StateConflict()
        rows = uow.session.execute(
            select(DisclosureSectionModel, DisclosureFieldModel)
            .join(
                DisclosureFieldModel, DisclosureFieldModel.section_id == DisclosureSectionModel.id
            )
            .where(DisclosureSectionModel.template_id == template.id)
            .order_by(DisclosureSectionModel.display_order)
        ).all()
        registry = {
            (section.section_code, field.source_fact_type): (section, field)
            for section, field in rows
        }
        required_sources = {
            ("BALANCE_SHEET", "STATEMENT_LINE"),
            ("BALANCE_SHEET", "GL_ACCOUNT"),
            ("INCOME_STATEMENT", "STATEMENT_LINE"),
            ("INCOME_STATEMENT", "GL_ACCOUNT"),
            ("CASH_FLOW", "CASH_FLOW_LINE"),
            ("CHANGES_IN_EQUITY", "EQUITY_LINE"),
        }
        if (
            set(registry) != required_sources
            or len(rows) != len(registry)
            or any(
                field.data_type != "DECIMAL"
                or not field.required
                or field.aggregation_handler_key
                != (
                    "SUM_STATEMENT_SOURCES"
                    if field.source_fact_type == "GL_ACCOUNT"
                    else "COPY_VERIFIED_LINE"
                )
                or section.requirement_rule_key != "SOURCE_STATEMENT_REQUIRED"
                for section, field in rows
            )
        ):
            raise StateConflict()
        return template, registry

    def templates(self, actor: Principal, company: UUID) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            rows = uow.session.scalars(
                select(DisclosureTemplateModel).where(DisclosureTemplateModel.status == "ACTIVE")
            )
            result: list[dict[str, object]] = []
            for template in rows:
                sections = list(
                    uow.session.scalars(
                        select(DisclosureSectionModel)
                        .where(DisclosureSectionModel.template_id == template.id)
                        .order_by(DisclosureSectionModel.display_order)
                    )
                )
                result.append(
                    {
                        **_serialize(template),
                        "sections": [
                            {
                                **_serialize(section),
                                "fields": [
                                    _serialize(field)
                                    for field in uow.session.scalars(
                                        select(DisclosureFieldModel).where(
                                            DisclosureFieldModel.section_id == section.id
                                        )
                                    )
                                ],
                            }
                            for section in sections
                        ],
                    }
                )
            return result

    def _sources(
        self, uow: CashFlowUnitOfWork, company: UUID, period_id: UUID
    ) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
        period = uow.periods.get(company_id=company, resource_id=period_id)
        if period is None:
            raise ResourceNotFound()
        issues: list[str] = []
        if period.status != "CLOSED":
            issues.append("PERIOD_NOT_CLOSED")
        statement_set = next(
            (
                item
                for item in uow.statements.sets(company, period_id)
                if item.close_version == period.close_version
            ),
            None,
        )
        if statement_set is None:
            issues.append("STATEMENT_SET_MISSING")
        balance = income = None
        if statement_set is not None:
            balance = uow.statements.statement(company, statement_set.id, "BALANCE_SHEET")
            income = uow.statements.statement(company, statement_set.id, "INCOME_STATEMENT")
        if balance is None:
            issues.append("BALANCE_SHEET_SOURCE_REQUIRED")
        if income is None:
            issues.append("INCOME_STATEMENT_SOURCE_REQUIRED")
        cash = uow.session.scalar(
            select(CashFlowStatementModel)
            .where(
                CashFlowStatementModel.company_id == company,
                CashFlowStatementModel.period_id == period_id,
            )
            .order_by(CashFlowStatementModel.generated_at.desc())
            .limit(1)
        )
        equity = uow.session.scalar(
            select(EquityStatementModel)
            .where(
                EquityStatementModel.company_id == company,
                EquityStatementModel.period_id == period_id,
            )
            .order_by(EquityStatementModel.generated_at.desc())
            .limit(1)
        )
        if cash is None or cash.status != "RECONCILED":
            issues.append("CASH_FLOW_SOURCE_REQUIRED")
        elif (
            statement_set is None
            or cash.statement_set_id != statement_set.id
            or cash.close_version != period.close_version
            or balance is None
            or income is None
            or cash.balance_sheet_digest != balance.snapshot_digest
            or cash.income_statement_digest != income.snapshot_digest
        ):
            issues.append("CASH_FLOW_SOURCE_STALE")
        if equity is None or equity.status != "RECONCILED":
            issues.append("EQUITY_SOURCE_REQUIRED")
        elif (
            statement_set is None
            or equity.statement_set_id != statement_set.id
            or equity.close_version != period.close_version
            or balance is None
            or income is None
            or equity.balance_sheet_digest != balance.snapshot_digest
            or equity.income_statement_digest != income.snapshot_digest
        ):
            issues.append("EQUITY_SOURCE_STALE")
        if period.status == "CLOSED" and statement_set is not None:
            try:
                bridge = CashFlowService(self.factory)._indirect_bridge(uow, company, period_id)
                if bridge.status != "READY" or bridge.issues:
                    issues.extend(issue.code for issue in bridge.issues)
                    if not bridge.issues:
                        issues.append("CASH_FLOW_SOURCE_STALE")
                if cash is not None and (
                    cash.statement_set_id != bridge.statement_set_id
                    or cash.close_version != bridge.close_version
                    or cash.source_digest != bridge.source_digest
                    or cash.mapping_digest != bridge.mapping_digest
                ):
                    issues.append("CASH_FLOW_SOURCE_STALE")
                equity_result = EquityService(self.factory)._calculate(uow, company, period_id)
                equity_issues = equity_result[-1]
                if equity_issues:
                    issues.extend(equity_issues)
                if equity is not None and equity.snapshot_digest != equity_result[7]:
                    issues.append("EQUITY_SOURCE_STALE")
            except (ClosingRunStale, ReportSourceStale, StateConflict):
                issues.append("REPORT_SOURCE_STALE")
        reconciliation_facts: list[tuple[str, str, str]] = []
        for view in (balance, income):
            if view is None:
                continue
            leaf_ids = {line.id for line in view.lines if line.subtotal_type == "LEAF"}
            source_rows = uow.session.scalars(
                select(StatementSourceModel).where(
                    StatementSourceModel.company_id == company,
                    StatementSourceModel.statement_line_id.in_(leaf_ids or {UUID(int=0)}),
                )
            )
            totals: dict[UUID, Decimal] = {}
            for source_row in source_rows:
                totals[source_row.statement_line_id] = (
                    totals.get(source_row.statement_line_id, Decimal("0")) + source_row.amount
                )
            if any(
                line.current_amount != totals.get(line.id, Decimal("0"))
                for line in view.lines
                if line.subtotal_type == "LEAF"
            ):
                issues.append("DISCLOSURE_GL_SOURCE_MISMATCH")
        if balance is not None:
            balance_amounts = {line.line_code: line.current_amount for line in balance.lines}
            assets = balance_amounts.get("ASSETS")
            liabilities_equity = balance_amounts.get("LIABILITIES_EQUITY")
            if assets is None or liabilities_equity is None or assets != liabilities_equity:
                issues.append("DISCLOSURE_RECONCILIATION_MISMATCH")
            else:
                reconciliation_facts.append(("BALANCE_SHEET", "ASSETS", str(assets)))
                reconciliation_facts.append(
                    ("BALANCE_SHEET", "LIABILITIES_EQUITY", str(liabilities_equity))
                )
        if income is not None and cash is not None:
            net_profit = next(
                (line.current_amount for line in income.lines if line.line_code == "NET_PROFIT"),
                None,
            )
            if net_profit is None or cash.net_profit != net_profit:
                issues.append("DISCLOSURE_RECONCILIATION_MISMATCH")
            else:
                reconciliation_facts.append(("INCOME_STATEMENT", "NET_PROFIT", str(net_profit)))
        if balance is not None and equity is not None:
            balance_equity = next(
                (line.current_amount for line in balance.lines if line.line_code == "EQUITY"),
                None,
            )
            equity_closing = sum(
                uow.session.scalars(
                    select(EquityStatementLineModel.amount).where(
                        EquityStatementLineModel.company_id == company,
                        EquityStatementLineModel.statement_id == equity.id,
                        EquityStatementLineModel.movement_type == "CLOSING",
                    )
                ),
                Decimal("0"),
            )
            if balance_equity is None or balance_equity != equity_closing:
                issues.append("DISCLOSURE_RECONCILIATION_MISMATCH")
            else:
                reconciliation_facts.append(("BALANCE_SHEET", "EQUITY", str(balance_equity)))
        template = None
        template_registry = None
        if period.status == "CLOSED":
            try:
                template, template_registry = self._template(
                    uow, period.start_date, period.end_date
                )
            except StateConflict:
                issues.append("DISCLOSURE_TEMPLATE_REQUIRED")
        if issues:
            return None, tuple(dict.fromkeys(issues))
        assert statement_set is not None and balance is not None and income is not None
        assert cash is not None and equity is not None and template is not None
        source_digest = digest(
            (
                str(statement_set.id),
                statement_set.close_version,
                balance.snapshot_digest,
                income.snapshot_digest,
                cash.snapshot_digest,
                equity.snapshot_digest,
                str(template.id),
                template.version,
            )
        )
        reconciliation_digest = digest((source_digest, reconciliation_facts))
        return {
            "statement_set_id": statement_set.id,
            "period": period,
            "balance": balance,
            "income": income,
            "cash": cash,
            "equity": equity,
            "template": template,
            "template_registry": template_registry,
            "source_digest": source_digest,
            "reconciliation_status": "RECONCILED",
            "reconciliation_digest": reconciliation_digest,
        }, ()

    def readiness(self, actor: Principal, company: UUID, period_id: UUID) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            sources, issues = self._sources(uow, company, period_id)
            return {
                "period_id": period_id,
                "status": "READY" if sources else "BLOCKED",
                "issues": issues,
                "statement_set_id": sources["statement_set_id"] if sources else None,
                "source_digest": sources["source_digest"] if sources else None,
                "template_id": sources["template"].id if sources else None,
                "template_version": sources["template"].version if sources else None,
                "validation_status": "INTERNAL_VALIDATION_ONLY",
            }

    def generate(
        self, actor: Principal, company: UUID, period_id: UUID, key: str
    ) -> dict[str, object]:
        if not key or len(key) > 100:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "disclosure.edit")
            uow.session.scalar(
                select(PeriodModel)
                .where(PeriodModel.company_id == company, PeriodModel.id == period_id)
                .with_for_update()
            )
            sources, issues = self._sources(uow, company, period_id)
            if sources is None:
                return {
                    "period_id": period_id,
                    "status": "BLOCKED",
                    "issues": issues,
                    "instance_id": None,
                    "validation_status": "INTERNAL_VALIDATION_ONLY",
                }
            uow.lock_command(company, actor.user_id, "disclosure.generate", key)
            fingerprint = digest(("disclosure.generate", str(period_id), sources["source_digest"]))
            command = uow.session.scalar(
                select(DisclosureCommandModel).where(
                    DisclosureCommandModel.company_id == company,
                    DisclosureCommandModel.actor_id == actor.user_id,
                    DisclosureCommandModel.idempotency_key == key,
                )
            )
            if command is not None:
                if command.fingerprint != fingerprint:
                    raise StateConflict()
                replay = uow.session.scalar(
                    select(DisclosureInstanceModel).where(
                        DisclosureInstanceModel.company_id == company,
                        DisclosureInstanceModel.id == command.instance_id,
                    )
                )
                if replay is None:
                    raise ResourceNotFound()
                return self._detail(uow, company, replay, sources)
            template = sources["template"]
            registry = sources["template_registry"]
            existing = uow.session.scalar(
                select(DisclosureInstanceModel)
                .where(
                    DisclosureInstanceModel.company_id == company,
                    DisclosureInstanceModel.period_id == period_id,
                    DisclosureInstanceModel.source_digest == sources["source_digest"],
                )
                .order_by(DisclosureInstanceModel.revision.desc())
            )
            if existing is not None:
                uow.session.add(
                    DisclosureCommandModel(
                        id=uuid4(),
                        company_id=company,
                        actor_id=actor.user_id,
                        idempotency_key=key,
                        fingerprint=fingerprint,
                        instance_id=existing.id,
                        created_at=uow.now(),
                    )
                )
                uow.session.flush()
                return self._detail(uow, company, existing, sources)
            now = uow.now()
            previous_revision = uow.session.scalar(
                select(DisclosureInstanceModel.revision)
                .where(
                    DisclosureInstanceModel.company_id == company,
                    DisclosureInstanceModel.period_id == period_id,
                )
                .order_by(DisclosureInstanceModel.revision.desc())
                .limit(1)
            )
            instance = DisclosureInstanceModel(
                id=uuid4(),
                company_id=company,
                statement_set_id=sources["statement_set_id"],
                period_id=period_id,
                template_id=template.id,
                template_version=template.version,
                revision=(previous_revision or 0) + 1,
                status="DRAFT",
                balance_sheet_digest=sources["balance"].snapshot_digest,
                income_statement_digest=sources["income"].snapshot_digest,
                cash_flow_digest=sources["cash"].snapshot_digest,
                equity_digest=sources["equity"].snapshot_digest,
                source_digest=sources["source_digest"],
                reconciliation_status=sources["reconciliation_status"],
                reconciliation_digest=sources["reconciliation_digest"],
                created_by=actor.user_id,
                created_at=now,
                approved_by=None,
                approved_at=None,
                version=1,
            )
            uow.session.add(instance)
            uow.session.flush()
            facts: list[tuple[str, UUID, str, str, Decimal, UUID | None, UUID]] = []
            for view in (sources["balance"], sources["income"]):
                for line in view.lines:
                    facts.append(
                        (
                            view.statement_type,
                            line.id,
                            line.line_code,
                            line.label,
                            line.current_amount,
                            None,
                            UUID(int=0),
                        )
                    )
            for line in uow.session.scalars(
                select(CashFlowLineModel)
                .where(
                    CashFlowLineModel.company_id == company,
                    CashFlowLineModel.statement_id == sources["cash"].id,
                )
                .order_by(CashFlowLineModel.display_order)
            ):
                facts.append(
                    (
                        "CASH_FLOW",
                        line.id,
                        line.line_code,
                        line.line_code,
                        line.amount,
                        None,
                        UUID(int=0),
                    )
                )
            equity_lines = uow.session.execute(
                select(EquityStatementLineModel, EquityComponentModel)
                .join(
                    EquityComponentModel,
                    EquityComponentModel.id == EquityStatementLineModel.component_id,
                )
                .where(
                    EquityStatementLineModel.company_id == company,
                    EquityStatementLineModel.statement_id == sources["equity"].id,
                )
                .order_by(EquityStatementLineModel.display_order)
            )
            for line, component in equity_lines:
                facts.append(
                    (
                        "CHANGES_IN_EQUITY",
                        line.id,
                        f"{component.component_code}.{line.movement_type}",
                        f"{component.name} · {line.movement_type}",
                        line.amount,
                        None,
                        UUID(int=0),
                    )
                )
            for view in (sources["balance"], sources["income"]):
                line_ids = {line.id for line in view.lines}
                source_rows = list(
                    uow.session.scalars(
                        select(StatementSourceModel).where(
                            StatementSourceModel.company_id == company,
                            StatementSourceModel.statement_line_id.in_(line_ids or {UUID(int=0)}),
                        )
                    )
                )
                grouped: dict[tuple[UUID, UUID], Decimal] = {}
                for source_row in source_rows:
                    key_pair = (source_row.statement_line_id, source_row.account_id)
                    grouped[key_pair] = grouped.get(key_pair, Decimal("0")) + source_row.amount
                accounts = {
                    account.id: account
                    for account in uow.session.scalars(
                        select(AccountModel).where(
                            AccountModel.company_id == company,
                            AccountModel.id.in_(
                                {account_id for _, account_id in grouped} or {UUID(int=0)}
                            ),
                        )
                    )
                }
                line_codes = {line.id: line.line_code for line in view.lines}
                for (line_id, group_account_id), amount in grouped.items():
                    account = accounts.get(group_account_id)
                    if account is None:
                        raise StateConflict()
                    facts.append(
                        (
                            view.statement_type,
                            group_account_id,
                            f"{line_codes[line_id]}.{account.account_code}",
                            account.account_name,
                            amount,
                            group_account_id,
                            line_id,
                        )
                    )
            for (
                source_type,
                source_id,
                source_code,
                label,
                amount,
                account_id,
                parent_line_id,
            ) in facts:
                section_code, fact_type = {
                    "BALANCE_SHEET": (
                        "BALANCE_SHEET",
                        "GL_ACCOUNT" if account_id else "STATEMENT_LINE",
                    ),
                    "INCOME_STATEMENT": (
                        "INCOME_STATEMENT",
                        "GL_ACCOUNT" if account_id else "STATEMENT_LINE",
                    ),
                    "CASH_FLOW": ("CASH_FLOW", "CASH_FLOW_LINE"),
                    "CHANGES_IN_EQUITY": ("CHANGES_IN_EQUITY", "EQUITY_LINE"),
                }[source_type]
                section, field = registry[(section_code, fact_type)]
                statement_line_id = (
                    parent_line_id
                    if account_id
                    else source_id
                    if source_type in {"BALANCE_SHEET", "INCOME_STATEMENT"}
                    else None
                )
                cash_flow_line_id = source_id if source_type == "CASH_FLOW" else None
                equity_line_id = source_id if source_type == "CHANGES_IN_EQUITY" else None
                uow.session.add(
                    DisclosureValueModel(
                        id=uuid4(),
                        company_id=company,
                        instance_id=instance.id,
                        section_id=section.id,
                        field_id=field.id,
                        source_type=source_type,
                        source_id=source_id,
                        statement_line_id=statement_line_id,
                        cash_flow_line_id=cash_flow_line_id,
                        equity_line_id=equity_line_id,
                        account_id=account_id,
                        source_code=source_code,
                        label=label,
                        decimal_value=amount,
                        validation_status="VALIDATED",
                    )
                )
            uow.session.flush()
            uow.session.add(
                DisclosureAuditModel(
                    id=uuid4(),
                    company_id=company,
                    instance_id=instance.id,
                    actor_id=actor.user_id,
                    action="GENERATED",
                    from_status=None,
                    to_status="DRAFT",
                    expected_version=1,
                    created_at=now,
                )
            )
            uow.session.add(
                DisclosureCommandModel(
                    id=uuid4(),
                    company_id=company,
                    actor_id=actor.user_id,
                    idempotency_key=key,
                    fingerprint=fingerprint,
                    instance_id=instance.id,
                    created_at=now,
                )
            )
            uow.session.flush()
            return self._detail(uow, company, instance, sources)

    def list(self, actor: Principal, company: UUID, period_id: UUID) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return [
                _serialize(row)
                for row in uow.session.scalars(
                    select(DisclosureInstanceModel)
                    .where(
                        DisclosureInstanceModel.company_id == company,
                        DisclosureInstanceModel.period_id == period_id,
                    )
                    .order_by(DisclosureInstanceModel.revision.desc())
                )
            ]

    def detail(self, actor: Principal, company: UUID, instance_id: UUID) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            instance = uow.session.scalar(
                select(DisclosureInstanceModel).where(
                    DisclosureInstanceModel.company_id == company,
                    DisclosureInstanceModel.id == instance_id,
                )
            )
            if instance is None:
                raise ResourceNotFound()
            sources, issues = self._sources(uow, company, instance.period_id)
            detail = self._detail(uow, company, instance, sources)
            detail["current_source_issues"] = issues
            return detail

    def source(
        self, actor: Principal, company: UUID, instance_id: UUID, value_id: UUID
    ) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            value = uow.session.scalar(
                select(DisclosureValueModel).where(
                    DisclosureValueModel.company_id == company,
                    DisclosureValueModel.instance_id == instance_id,
                    DisclosureValueModel.id == value_id,
                )
            )
            if value is None:
                raise ResourceNotFound()
            instance = uow.session.scalar(
                select(DisclosureInstanceModel).where(
                    DisclosureInstanceModel.company_id == company,
                    DisclosureInstanceModel.id == value.instance_id,
                )
            )
            if instance is None:
                raise ResourceNotFound()
            result: dict[str, object] = {
                "source_type": value.source_type,
                "source_id": value.source_id,
                "source_code": value.source_code,
                "amount": value.decimal_value,
                "journal_ids": [],
                "journal_line_ids": [],
                "evidence_ids": [],
                "statement_set_id": instance.statement_set_id,
                "source_path": None,
                "validation_status": "INTERNAL_VALIDATION_ONLY",
            }
            journal_ids: set[UUID] = set()
            journal_line_ids: set[UUID] = set()
            evidence_ids: set[UUID] = set()
            if value.source_type in {"BALANCE_SHEET", "INCOME_STATEMENT"}:
                result["source_path"] = (
                    f"/financial-statements/sets/{instance.statement_set_id}/drilldown"
                    f"?statement_type={value.source_type}&line_code={value.source_code}"
                )
                source_rows = list(
                    uow.session.scalars(
                        select(StatementSourceModel).where(
                            StatementSourceModel.company_id == company,
                            StatementSourceModel.statement_line_id
                            == (value.statement_line_id or value.source_id),
                            *(
                                [StatementSourceModel.account_id == value.account_id]
                                if value.account_id is not None
                                else []
                            ),
                        )
                    )
                )
                if value.account_id is not None:
                    account = uow.session.scalar(
                        select(AccountModel).where(
                            AccountModel.company_id == company,
                            AccountModel.id == value.account_id,
                        )
                    )
                    if account is None:
                        raise ResourceNotFound()
                    result["account_id"] = account.id
                    result["account_code"] = account.account_code
                    result["account_name"] = account.account_name
                    statement_line_code = value.source_code.split(".", 1)[0]
                    result["source_path"] = (
                        f"/financial-statements/sets/{instance.statement_set_id}/drilldown"
                        f"?statement_type={value.source_type}&line_code={statement_line_code}"
                    )
                for row in source_rows:
                    journal_line_ids.add(row.journal_line_id)
                # Journal identity is resolved from the company scoped line relation.
                from app.accounting.journals.infrastructure.models import JournalLineModel

                lines = list(
                    uow.session.scalars(
                        select(JournalLineModel).where(
                            JournalLineModel.company_id == company,
                            JournalLineModel.id.in_(journal_line_ids or {UUID(int=0)}),
                        )
                    )
                )
                journal_ids = {line.journal_entry_id for line in lines}
                for journal_id in journal_ids:
                    evidence_ids.update(
                        uow.session.scalars(
                            select(JournalEvidenceModel.evidence_id).where(
                                JournalEvidenceModel.company_id == company,
                                JournalEvidenceModel.journal_entry_id == journal_id,
                            )
                        )
                    )
            elif value.source_type == "CASH_FLOW":
                line = uow.session.scalar(
                    select(CashFlowLineModel).where(
                        CashFlowLineModel.company_id == company,
                        CashFlowLineModel.id == value.source_id,
                    )
                )
                if line is None:
                    raise ResourceNotFound()
                result["source_path"] = (
                    f"/cash-flow/{line.statement_id}/drilldown?line_id={line.id}"
                )
                if line.event_id is not None:
                    event = uow.session.scalar(
                        select(CashFlowEventModel).where(
                            CashFlowEventModel.company_id == company,
                            CashFlowEventModel.id == line.event_id,
                        )
                    )
                    if event is not None:
                        journal_ids.add(event.journal_id)
                        journal_line_ids.update((event.cash_line_id, event.counterpart_line_id))
                        if event.evidence_id:
                            evidence_ids.add(event.evidence_id)
                if line.adjustment_id is not None:
                    traces = uow.session.scalars(
                        select(CashFlowAdjustmentSourceModel).where(
                            CashFlowAdjustmentSourceModel.company_id == company,
                            CashFlowAdjustmentSourceModel.adjustment_id == line.adjustment_id,
                        )
                    )
                    journal_ids.update(trace.journal_id for trace in traces)
                    journal_line_ids.update(trace.journal_line_id for trace in traces)
            elif value.source_type == "CHANGES_IN_EQUITY":
                from app.reporting.equity.models import EquityStatementSourceModel

                equity_line = uow.session.scalar(
                    select(EquityStatementLineModel).where(
                        EquityStatementLineModel.company_id == company,
                        EquityStatementLineModel.id == value.source_id,
                    )
                )
                if equity_line is None:
                    raise ResourceNotFound()
                result["source_path"] = (
                    f"/equity/statements/{equity_line.statement_id}/lines/{equity_line.id}/sources"
                )

                equity_sources = uow.session.scalars(
                    select(EquityStatementSourceModel).where(
                        EquityStatementSourceModel.company_id == company,
                        EquityStatementSourceModel.statement_line_id == value.source_id,
                    )
                )
                for equity_source in equity_sources:
                    if equity_source.journal_line_id:
                        journal_line_ids.add(equity_source.journal_line_id)
                    elif equity_source.income_statement_id:
                        result["income_statement_id"] = equity_source.income_statement_id
                if journal_line_ids:
                    from app.accounting.journals.infrastructure.models import JournalLineModel

                    journal_rows = uow.session.scalars(
                        select(JournalLineModel).where(
                            JournalLineModel.company_id == company,
                            JournalLineModel.id.in_(journal_line_ids),
                        )
                    )
                    journal_ids.update(line.journal_entry_id for line in journal_rows)
            for journal_id in journal_ids:
                if journal_id.int != 0:
                    evidence_ids.update(
                        uow.session.scalars(
                            select(JournalEvidenceModel.evidence_id).where(
                                JournalEvidenceModel.company_id == company,
                                JournalEvidenceModel.journal_entry_id == journal_id,
                            )
                        )
                    )
            result["journal_ids"] = sorted(journal_ids, key=str)
            result["journal_line_ids"] = sorted(journal_line_ids, key=str)
            result["evidence_ids"] = sorted(evidence_ids, key=str)
            return result

    def save_narrative(
        self,
        actor: Principal,
        company: UUID,
        instance_id: UUID,
        section_id: UUID,
        text_value: str,
        expected_version: int,
    ) -> dict[str, object]:
        if not text_value.strip() or len(text_value) > 4000 or expected_version < 1:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "disclosure.edit")
            instance = uow.session.scalar(
                select(DisclosureInstanceModel)
                .where(
                    DisclosureInstanceModel.company_id == company,
                    DisclosureInstanceModel.id == instance_id,
                )
                .with_for_update()
            )
            if instance is None:
                raise ResourceNotFound()
            if instance.version != expected_version:
                raise VersionConflict()
            if instance.status not in {"DRAFT", "REJECTED"}:
                raise StateConflict()
            sources, _issues = self._sources(uow, company, instance.period_id)
            if sources is None or sources["source_digest"] != instance.source_digest:
                raise DisclosureStale()
            section = uow.session.scalar(
                select(DisclosureSectionModel).where(
                    DisclosureSectionModel.template_id == instance.template_id,
                    DisclosureSectionModel.id == section_id,
                )
            )
            if section is None:
                raise ResourceNotFound()
            narrative = uow.session.scalar(
                select(DisclosureNarrativeModel)
                .where(
                    DisclosureNarrativeModel.company_id == company,
                    DisclosureNarrativeModel.instance_id == instance.id,
                    DisclosureNarrativeModel.section_id == section.id,
                )
                .with_for_update()
            )
            now = uow.now()
            if narrative is None:
                narrative = DisclosureNarrativeModel(
                    id=uuid4(),
                    company_id=company,
                    instance_id=instance.id,
                    section_id=section.id,
                    text_value=text_value.strip(),
                    status="DRAFT",
                    source_digest=instance.source_digest,
                    updated_by=actor.user_id,
                    updated_at=now,
                    version=1,
                )
                uow.session.add(narrative)
            elif narrative.status == "APPROVED":
                raise StateConflict()
            else:
                narrative.text_value = text_value.strip()
                narrative.source_digest = instance.source_digest
                narrative.updated_by = actor.user_id
                narrative.updated_at = now
                narrative.version += 1
            prior = instance.version
            instance.version += 1
            uow.session.add(
                DisclosureAuditModel(
                    id=uuid4(),
                    company_id=company,
                    instance_id=instance.id,
                    actor_id=actor.user_id,
                    action="NARRATIVE_SAVED",
                    from_status=instance.status,
                    to_status=instance.status,
                    expected_version=prior,
                    created_at=now,
                )
            )
            uow.session.flush()
            return {**_serialize(narrative), "instance_version": instance.version}

    def request_review(
        self, actor: Principal, company: UUID, instance_id: UUID, expected_version: int
    ) -> dict[str, object]:
        return self._transition(
            actor, company, instance_id, expected_version, "REVIEW_REQUESTED", "REVIEW_REQUESTED"
        )

    def approve(
        self, actor: Principal, company: UUID, instance_id: UUID, expected_version: int
    ) -> dict[str, object]:
        return self._transition(
            actor,
            company,
            instance_id,
            expected_version,
            "APPROVED",
            "APPROVED",
        )

    def reject(
        self,
        actor: Principal,
        company: UUID,
        instance_id: UUID,
        expected_version: int,
        reason: str,
    ) -> dict[str, object]:
        if not reason.strip() or len(reason) > 1000:
            raise InvalidInput()
        return self._transition(
            actor, company, instance_id, expected_version, "REJECTED", "REJECTED", reason.strip()
        )

    def _transition(
        self,
        actor: Principal,
        company: UUID,
        instance_id: UUID,
        expected_version: int,
        target: str,
        action: str,
        reason: str | None = None,
    ) -> dict[str, object]:
        if expected_version < 1:
            raise InvalidInput()
        with self.factory() as uow:
            permission = (
                "disclosure.approve" if target in {"APPROVED", "REJECTED"} else "disclosure.edit"
            )
            require_company(uow, actor, company, permission)
            instance = uow.session.scalar(
                select(DisclosureInstanceModel)
                .where(
                    DisclosureInstanceModel.company_id == company,
                    DisclosureInstanceModel.id == instance_id,
                )
                .with_for_update()
            )
            if instance is None:
                raise ResourceNotFound()
            if instance.version != expected_version:
                raise VersionConflict()
            if target == "REVIEW_REQUESTED":
                if instance.status not in {"DRAFT", "REJECTED"}:
                    raise StateConflict()
                narratives = list(
                    uow.session.scalars(
                        select(DisclosureNarrativeModel).where(
                            DisclosureNarrativeModel.company_id == company,
                            DisclosureNarrativeModel.instance_id == instance.id,
                        )
                    )
                )
                section_ids = set(
                    uow.session.scalars(
                        select(DisclosureSectionModel.id).where(
                            DisclosureSectionModel.template_id == instance.template_id
                        )
                    )
                )
                written = {row.section_id for row in narratives if row.text_value.strip()}
                if not section_ids or written != section_ids:
                    raise StateConflict()
            else:
                authors = set(
                    uow.session.scalars(
                        select(DisclosureNarrativeModel.updated_by).where(
                            DisclosureNarrativeModel.company_id == company,
                            DisclosureNarrativeModel.instance_id == instance.id,
                        )
                    )
                )
                if (
                    instance.status != "REVIEW_REQUESTED"
                    or actor.user_id == instance.created_by
                    or actor.user_id in authors
                ):
                    raise StateConflict()
            sources, _issues = self._sources(uow, company, instance.period_id)
            if sources is None or sources["source_digest"] != instance.source_digest:
                raise DisclosureStale()
            prior = instance.status
            now = uow.now()
            instance.status = target
            instance.version += 1
            if target == "APPROVED":
                instance.approved_by = actor.user_id
                instance.approved_at = now
                narratives = list(
                    uow.session.scalars(
                        select(DisclosureNarrativeModel)
                        .where(
                            DisclosureNarrativeModel.company_id == company,
                            DisclosureNarrativeModel.instance_id == instance.id,
                        )
                        .with_for_update()
                    )
                )
                for narrative in narratives:
                    if narrative.source_digest != instance.source_digest:
                        raise StateConflict()
                    narrative.status = "APPROVED"
                    narrative.version += 1
            uow.session.add(
                DisclosureAuditModel(
                    id=uuid4(),
                    company_id=company,
                    instance_id=instance.id,
                    actor_id=actor.user_id,
                    action=action,
                    from_status=prior,
                    to_status=target,
                    expected_version=expected_version,
                    created_at=now,
                    reason=reason,
                )
            )
            uow.session.flush()
            return self._detail(uow, company, instance, sources)

    def _detail(
        self,
        uow: CashFlowUnitOfWork,
        company: UUID,
        instance: DisclosureInstanceModel,
        current_sources: dict[str, Any] | None,
    ) -> dict[str, object]:
        stale = (
            current_sources is None or current_sources["source_digest"] != instance.source_digest
        )
        values = list(
            uow.session.scalars(
                select(DisclosureValueModel)
                .where(
                    DisclosureValueModel.company_id == company,
                    DisclosureValueModel.instance_id == instance.id,
                )
                .order_by(DisclosureValueModel.section_id, DisclosureValueModel.source_code)
            )
        )
        narratives = list(
            uow.session.scalars(
                select(DisclosureNarrativeModel)
                .where(
                    DisclosureNarrativeModel.company_id == company,
                    DisclosureNarrativeModel.instance_id == instance.id,
                )
                .order_by(DisclosureNarrativeModel.section_id)
            )
        )
        audits = list(
            uow.session.scalars(
                select(DisclosureAuditModel)
                .where(
                    DisclosureAuditModel.company_id == company,
                    DisclosureAuditModel.instance_id == instance.id,
                )
                .order_by(DisclosureAuditModel.created_at, DisclosureAuditModel.id)
            )
        )
        return {
            **_serialize(instance),
            "status": "STALE" if stale and instance.status != "APPROVED" else instance.status,
            "source_stale": stale,
            "values": [_serialize(value) for value in values],
            "narratives": [_serialize(narrative) for narrative in narratives],
            "audit_events": [_serialize(event) for event in audits],
            "validation_status": "INTERNAL_VALIDATION_ONLY",
        }
