"""Resolve company policy and pin an existing CLOSED statement snapshot."""

import re
from collections.abc import Callable
from datetime import date
from uuid import UUID, uuid4

from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.center.repository import ReportRun
from app.reporting.center.unit_of_work import ReportCenterUnitOfWork
from app.reporting.financial_metrics.rules import FORMULAS
from app.reporting.periods.rules import Preset, resolve

REPORTS = (
    ("BALANCE_SHEET", "재무상태표", "AS_OF"),
    ("INCOME_STATEMENT", "손익계산서", "RANGE"),
    ("FINANCIAL_METRICS", "재무비율", "RANGE"),
)
FORMATS = ("PDF", "XLSX", "CSV")


class ReportCenterService:
    def __init__(self, factory: Callable[[], ReportCenterUnitOfWork]) -> None:
        self.factory = factory

    def catalog(self, actor: Principal, company: UUID) -> tuple[dict[str, object], ...]:
        with self.factory() as uow:
            access = require_company(uow, actor, company, "report.read")
            return tuple(
                {
                    "code": code,
                    "label": label,
                    "period_mode": mode,
                    "formats": FORMATS,
                    "can_generate": "report.generate" in access.permissions
                    and "report.export" in access.permissions,
                }
                for code, label, mode in REPORTS
            )

    def request(
        self,
        actor: Principal,
        company: UUID,
        *,
        report_code: str,
        format: str,
        period_id: UUID,
        period_preset: Preset,
        key: str,
        date_from: date | None = None,
        date_to: date | None = None,
        as_of: date | None = None,
    ) -> ReportRun:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        modes = {code: mode for code, _, mode in REPORTS}
        if report_code not in modes or format not in FORMATS:
            raise InvalidInput()
        fingerprint = digest(
            (
                report_code,
                format,
                str(period_id),
                period_preset,
                date_from.isoformat() if date_from else None,
                date_to.isoformat() if date_to else None,
                as_of.isoformat() if as_of else None,
            )
        )
        with self.factory() as uow:
            access = require_company(uow, actor, company, "report.generate")
            require_company(uow, actor, company, "report.export")
            uow.lock_command(company, actor.user_id, "report.generate", key)
            replay = uow.report_runs.replay(company, actor.user_id, key, fingerprint)
            if replay is not None:
                return replay
            settings = uow.settings.get(company)
            period = uow.periods.get(company_id=company, resource_id=period_id)
            if settings is None or period is None:
                raise ResourceNotFound()
            resolved = resolve(
                period_preset,
                modes[report_code],  # type: ignore[arg-type]
                timezone=access.company.timezone,
                fiscal_year_start_month=settings.fiscal_year_start_month,
                week_start=settings.reporting_week_start,
                now=uow.now(),
                opening_date=access.company.opening_date,
                date_from=date_from,
                date_to=date_to,
                as_of=as_of,
            )
            if period.status != "CLOSED" or (
                resolved.as_of != period.end_date
                if modes[report_code] == "AS_OF"
                else (resolved.date_from, resolved.date_to) != (period.start_date, period.end_date)
            ):
                raise InvalidInput()
            statement_set = next(
                (
                    item
                    for item in uow.statements.sets(company, period_id)
                    if item.close_version == period.close_version
                ),
                None,
            )
            if statement_set is None:
                raise ResourceNotFound()
            balance = uow.statements.statement(company, statement_set.id, "BALANCE_SHEET")
            income = uow.statements.statement(company, statement_set.id, "INCOME_STATEMENT")
            if balance is None or income is None:
                raise ResourceNotFound()
            formula_version = max(formula.version for formula in FORMULAS)
            source = digest(
                (
                    str(statement_set.id),
                    statement_set.close_version,
                    statement_set.trial_balance_digest,
                    statement_set.mapping_digest,
                    statement_set.taxonomy_version,
                    balance.snapshot_digest,
                    income.snapshot_digest,
                    formula_version if report_code == "FINANCIAL_METRICS" else None,
                )
            )
            now = uow.now()
            run = ReportRun(
                id=uuid4(),
                company_id=company,
                report_code=report_code,
                format=format,
                period_preset=period_preset,
                period_mode=modes[report_code],
                date_from=resolved.date_from,
                date_to=resolved.date_to,
                as_of=resolved.as_of,
                period_id=period_id,
                statement_set_id=statement_set.id,
                close_version=statement_set.close_version,
                taxonomy_version=statement_set.taxonomy_version,
                trial_balance_digest=statement_set.trial_balance_digest,
                mapping_digest=statement_set.mapping_digest,
                balance_sheet_digest=balance.snapshot_digest,
                income_statement_digest=income.snapshot_digest,
                source_digest=source,
                template_version=1,
                status="REQUESTED",
                requested_by=actor.user_id,
                requested_at=now,
                started_at=None,
                completed_at=None,
                error_code=None,
                retry_of_run_id=None,
                version=1,
            )
            uow.report_runs.add(run, key, fingerprint)
            return run

    def get(self, actor: Principal, company: UUID, run_id: UUID) -> ReportRun:
        with self.factory() as uow:
            require_company(uow, actor, company, "report.read")
            result = uow.report_runs.get(company, run_id)
            if result is None:
                raise ResourceNotFound()
            return result

    def history(self, actor: Principal, company: UUID) -> list[ReportRun]:
        with self.factory() as uow:
            require_company(uow, actor, company, "report.download_history")
            return uow.report_runs.list(company)
