"""Resolve company policy and pin an existing CLOSED statement snapshot."""

import re
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select

from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.cash_flow.service import CashFlowService
from app.reporting.center.render import ReportDocument, render
from app.reporting.center.repository import ReportArtifact, ReportRun
from app.reporting.center.unit_of_work import ReportCenterUnitOfWork
from app.reporting.disclosures.models import (
    DisclosureInstanceModel,
    DisclosureNarrativeModel,
    DisclosureSectionModel,
    DisclosureValueModel,
)
from app.reporting.disclosures.service import DisclosureService
from app.reporting.equity.models import (
    EquityComponentModel,
    EquityStatementLineModel,
    EquityStatementModel,
)
from app.reporting.equity.service import MOVEMENTS, EquityService
from app.reporting.financial_metrics.rules import FORMULAS, calculate
from app.reporting.periods.rules import Preset, resolve
from app.storage.domain.contracts import ObjectStorage, StorageUnavailable

REPORTS = (
    ("BALANCE_SHEET", "재무상태표", "AS_OF"),
    ("INCOME_STATEMENT", "손익계산서", "RANGE"),
    ("FINANCIAL_METRICS", "재무비율", "RANGE"),
    ("CASH_FLOW", "현금흐름표", "RANGE"),
    ("CHANGES_IN_EQUITY", "자본변동표", "RANGE"),
    ("NOTES", "재무제표 주석", "RANGE"),
)
FORMATS = ("PDF", "XLSX", "CSV")


class ReportCenterService:
    def __init__(
        self, factory: Callable[[], ReportCenterUnitOfWork], storage: ObjectStorage
    ) -> None:
        self.factory = factory
        self.storage = storage

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
            cash = None
            equity = None
            notes = None
            if report_code == "CASH_FLOW":
                cash = uow.cash_snapshots.current(company, period_id)
                bridge = CashFlowService(self.factory)._indirect_bridge(uow, company, period_id)
                if (
                    bridge.status != "READY"
                    or bridge.issues
                    or (
                        cash.statement_set_id,
                        cash.close_version,
                        cash.source_digest,
                        cash.mapping_digest,
                        cash.balance_sheet_digest,
                        cash.income_statement_digest,
                    )
                    != (
                        statement_set.id,
                        period.close_version,
                        bridge.source_digest,
                        bridge.mapping_digest,
                        balance.snapshot_digest,
                        income.snapshot_digest,
                    )
                ):
                    raise StateConflict()
            if report_code == "CHANGES_IN_EQUITY":
                _, _, _, _, _, _, _, identity, _, _, issues = EquityService(
                    self.factory
                )._calculate(uow, company, period_id)
                if issues:
                    raise StateConflict()
                equity = uow.session.scalar(
                    select(EquityStatementModel).where(
                        EquityStatementModel.company_id == company,
                        EquityStatementModel.period_id == period_id,
                        EquityStatementModel.snapshot_digest == identity,
                    )
                )
                if equity is None:
                    raise StateConflict()
            if report_code == "NOTES":
                note_source, issues = DisclosureService(self.factory)._sources(
                    uow, company, period_id
                )
                if note_source is None or issues:
                    raise StateConflict()
                notes = uow.session.scalar(
                    select(DisclosureInstanceModel).where(
                        DisclosureInstanceModel.company_id == company,
                        DisclosureInstanceModel.period_id == period_id,
                        DisclosureInstanceModel.statement_set_id == statement_set.id,
                        DisclosureInstanceModel.source_digest == note_source["source_digest"],
                        DisclosureInstanceModel.status == "APPROVED",
                    )
                )
                if notes is None:
                    raise StateConflict()
                notes_equity = uow.session.scalar(
                    select(EquityStatementModel).where(
                        EquityStatementModel.company_id == company,
                        EquityStatementModel.period_id == period_id,
                        EquityStatementModel.snapshot_digest
                        == note_source["equity"].snapshot_digest,
                    )
                )
                if (
                    notes_equity is None
                    or notes_equity.statement_set_id != statement_set.id
                    or notes_equity.balance_sheet_digest != balance.snapshot_digest
                    or notes_equity.income_statement_digest != income.snapshot_digest
                    or notes_equity.status != "RECONCILED"
                ):
                    raise StateConflict()
            formula_version = max(formula.version for formula in FORMULAS)
            source_digest = (
                cash.snapshot_digest
                if cash is not None
                else equity.snapshot_digest
                if equity is not None
                else notes.source_digest
                if notes is not None
                else digest(
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
                source_digest=source_digest,
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

    def artifact(self, actor: Principal, company: UUID, run_id: UUID) -> ReportArtifact:
        with self.factory() as uow:
            require_company(uow, actor, company, "report.download_history")
            run = uow.report_runs.get(company, run_id)
            if run is None or run.status != "COMPLETED":
                raise ResourceNotFound()
            artifact = uow.report_runs.artifact(company, run_id)
            if artifact is None:
                raise ResourceNotFound()
            return artifact

    def download(
        self, actor: Principal, company: UUID, run_id: UUID
    ) -> tuple[bytes, ReportArtifact]:
        with self.factory() as uow:
            require_company(uow, actor, company, "report.read")
            require_company(uow, actor, company, "report.download_history")
            run = uow.report_runs.get(company, run_id)
            if run is None or run.status != "COMPLETED":
                raise ResourceNotFound()
            artifact = uow.report_runs.artifact(company, run_id)
            if artifact is None:
                raise ResourceNotFound()
            content = self.storage.read(company, artifact.storage_key)
            if (
                len(content) != artifact.size_bytes
                or sha256(content).hexdigest() != artifact.file_sha256
            ):
                raise StorageUnavailable()
            return content, artifact

    def generate(self, actor: Principal, company: UUID, run_id: UUID) -> ReportRun:
        storage_key: str | None = None
        failure: str | None = None
        try:
            with self.factory() as uow:
                access = require_company(uow, actor, company, "report.generate")
                require_company(uow, actor, company, "report.export")
                run = uow.report_runs.get(company, run_id, lock=True)
                if run is None:
                    raise ResourceNotFound()
                if run.status == "COMPLETED":
                    return run
                if run.status != "REQUESTED":
                    raise StateConflict()
                uow.report_runs.mark_started(company, run_id, uow.now())
                try:
                    document = self._document(uow, run, access.company.company_name)
                    content, content_type, extension = render(document, run.format)
                    file_name = f"{run.report_code.lower()}_{run.id.hex}.{extension}"
                    storage_key = self.storage.put(company, content)
                except (ResourceNotFound, StateConflict):
                    failure = "REPORT_SOURCE_STALE"
                    raise _GenerationFailed() from None
                except StorageUnavailable:
                    failure = "STORAGE_UNAVAILABLE"
                    raise _GenerationFailed() from None
                except Exception:
                    failure = "EXPORT_GENERATION_FAILED"
                    raise _GenerationFailed() from None
                uow.report_runs.complete(
                    run,
                    storage_key=storage_key,
                    file_name=file_name,
                    file_sha256=sha256(content).hexdigest(),
                    size_bytes=len(content),
                    content_type=content_type,
                    now=uow.now(),
                )
        except _GenerationFailed:
            with self.factory() as uow:
                uow.report_runs.fail(
                    company, run_id, failure or "EXPORT_GENERATION_FAILED", uow.now()
                )
        except Exception:
            if storage_key is not None:
                self.storage.delete(company, storage_key)
            raise
        return self.get(actor, company, run_id)

    def retry(self, actor: Principal, company: UUID, run_id: UUID, key: str) -> ReportRun:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        fingerprint = digest(("report.retry", str(run_id)))
        with self.factory() as uow:
            require_company(uow, actor, company, "report.generate")
            require_company(uow, actor, company, "report.export")
            uow.lock_command(company, actor.user_id, "report.generate", key)
            replay = uow.report_runs.replay(company, actor.user_id, key, fingerprint)
            if replay is not None:
                return replay
            old = uow.report_runs.get(company, run_id)
            if old is None:
                raise ResourceNotFound()
            if old.status != "FAILED":
                raise StateConflict()
            fresh = replace(
                old,
                id=uuid4(),
                status="REQUESTED",
                requested_by=actor.user_id,
                requested_at=uow.now(),
                started_at=None,
                completed_at=None,
                error_code=None,
                retry_of_run_id=old.id,
                version=1,
            )
            uow.report_runs.add(fresh, key, fingerprint)
            return fresh

    @staticmethod
    def _document(uow: ReportCenterUnitOfWork, run: ReportRun, company_name: str) -> ReportDocument:
        statement_set = uow.statements.set(run.company_id, run.statement_set_id)
        if (
            statement_set is None
            or statement_set.close_version != run.close_version
            or statement_set.trial_balance_digest != run.trial_balance_digest
            or statement_set.mapping_digest != run.mapping_digest
            or statement_set.taxonomy_version != run.taxonomy_version
        ):
            raise StateConflict()
        balance = uow.statements.statement(run.company_id, statement_set.id, "BALANCE_SHEET")
        income = uow.statements.statement(run.company_id, statement_set.id, "INCOME_STATEMENT")
        if (
            balance is None
            or income is None
            or balance.snapshot_digest != run.balance_sheet_digest
            or income.snapshot_digest != run.income_statement_digest
        ):
            raise StateConflict()
        if run.report_code not in {"CASH_FLOW", "CHANGES_IN_EQUITY", "NOTES"}:
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
                    formula_version if run.report_code == "FINANCIAL_METRICS" else None,
                )
            )
            if source != run.source_digest:
                raise StateConflict()
        metadata: tuple[tuple[str, str], ...] = (
            ("company", company_name),
            ("report", run.report_code),
            ("period", str(run.as_of or f"{run.date_from}/{run.date_to}")),
            ("generated_at", run.requested_at.isoformat()),
            ("statement_set_id", str(statement_set.id)),
            ("snapshot_version", str(run.close_version)),
            ("source_digest", run.source_digest),
        )
        columns: tuple[str, ...]
        rows: tuple[tuple[str, ...], ...]
        sections: tuple[tuple[str, tuple[str, ...], tuple[tuple[str, ...], ...]], ...] = ()
        if run.report_code == "CHANGES_IN_EQUITY":
            equity = uow.session.scalar(
                select(EquityStatementModel).where(
                    EquityStatementModel.company_id == run.company_id,
                    EquityStatementModel.period_id == run.period_id,
                    EquityStatementModel.statement_set_id == run.statement_set_id,
                    EquityStatementModel.snapshot_digest == run.source_digest,
                )
            )
            if (
                equity is None
                or equity.status != "RECONCILED"
                or equity.balance_sheet_digest != run.balance_sheet_digest
                or equity.income_statement_digest != run.income_statement_digest
            ):
                raise StateConflict()
            components = list(
                uow.session.scalars(
                    select(EquityComponentModel)
                    .where(
                        EquityComponentModel.company_id == run.company_id,
                        EquityComponentModel.id.in_(
                            select(EquityStatementLineModel.component_id).where(
                                EquityStatementLineModel.company_id == run.company_id,
                                EquityStatementLineModel.statement_id == equity.id,
                            )
                        ),
                    )
                    .order_by(EquityComponentModel.display_order, EquityComponentModel.id)
                )
            )
            saved_lines = list(
                uow.session.scalars(
                    select(EquityStatementLineModel).where(
                        EquityStatementLineModel.company_id == run.company_id,
                        EquityStatementLineModel.statement_id == equity.id,
                    )
                )
            )
            amounts = {(line.component_id, line.movement_type): line.amount for line in saved_lines}
            columns = ("movement_type", *(component.component_code for component in components))
            rows = tuple(
                (
                    movement,
                    *(format(amounts[(component.id, movement)], "f") for component in components),
                )
                for movement in MOVEMENTS
            )
            sections = (
                (
                    "Components",
                    ("component_code", "name"),
                    tuple((component.component_code, component.name) for component in components),
                ),
            )
            metadata += (
                ("equity_snapshot_id", str(equity.id)),
                ("equity_snapshot_generated_at", equity.generated_at.isoformat()),
                ("equity_validation", "INTERNAL_VALIDATION_ONLY"),
            )
        elif run.report_code == "NOTES":
            current, issues = DisclosureService(lambda: uow)._sources(
                uow, run.company_id, run.period_id
            )
            note = uow.session.scalar(
                select(DisclosureInstanceModel).where(
                    DisclosureInstanceModel.company_id == run.company_id,
                    DisclosureInstanceModel.period_id == run.period_id,
                    DisclosureInstanceModel.statement_set_id == run.statement_set_id,
                    DisclosureInstanceModel.source_digest == run.source_digest,
                    DisclosureInstanceModel.status == "APPROVED",
                )
            )
            if (
                current is None
                or issues
                or current["source_digest"] != run.source_digest
                or note is None
            ):
                raise StateConflict()
            note_values = list(
                uow.session.scalars(
                    select(DisclosureValueModel)
                    .where(
                        DisclosureValueModel.company_id == run.company_id,
                        DisclosureValueModel.instance_id == note.id,
                    )
                    .order_by(DisclosureValueModel.section_id, DisclosureValueModel.source_code)
                )
            )
            sections_by_id = {
                row.id: row.title
                for row in uow.session.scalars(
                    select(DisclosureSectionModel).where(
                        DisclosureSectionModel.template_id == note.template_id
                    )
                )
            }
            narratives = list(
                uow.session.scalars(
                    select(DisclosureNarrativeModel)
                    .where(
                        DisclosureNarrativeModel.company_id == run.company_id,
                        DisclosureNarrativeModel.instance_id == note.id,
                    )
                    .order_by(DisclosureNarrativeModel.section_id)
                )
            )
            if any(
                row.status != "APPROVED" or row.source_digest != note.source_digest
                for row in narratives
            ):
                raise StateConflict()
            columns = (
                "section",
                "source_type",
                "source_code",
                "label",
                "amount",
                "source_id",
                "statement_line_id",
                "account_id",
            )
            value_rows: list[tuple[str, ...]] = []
            for value in note_values:
                if value.decimal_value is None:
                    raise StateConflict()
                value_rows.append(
                    (
                        sections_by_id[value.section_id],
                        value.source_type,
                        value.source_code,
                        value.label,
                        format(value.decimal_value, "f"),
                        str(value.source_id),
                        str(value.statement_line_id) if value.statement_line_id else "",
                        str(value.account_id) if value.account_id else "",
                    )
                )
            rows = tuple(value_rows)
            sections = (
                (
                    "ApprovedNarratives",
                    ("section", "text", "source_digest"),
                    tuple(
                        (sections_by_id[row.section_id], row.text_value, row.source_digest)
                        for row in narratives
                    ),
                ),
            )
            if note.approved_at is None or note.approved_by is None:
                raise StateConflict()
            metadata += (
                ("disclosure_instance_id", str(note.id)),
                ("disclosure_revision", str(note.revision)),
                ("disclosure_template_version", str(note.template_version)),
                ("disclosure_approved_by", str(note.approved_by)),
                ("disclosure_approved_at", note.approved_at.isoformat()),
                ("disclosure_validation", "INTERNAL_VALIDATION_ONLY"),
            )
        elif run.report_code == "CASH_FLOW":
            cash = uow.cash_snapshots.by_digest(run.company_id, run.period_id, run.source_digest)
            if (
                cash.statement_set_id != run.statement_set_id
                or cash.close_version != run.close_version
                or cash.balance_sheet_digest != run.balance_sheet_digest
                or cash.income_statement_digest != run.income_statement_digest
                or cash.status != "RECONCILED"
            ):
                raise StateConflict()
            columns = ("line_code", "amount", "source_type")
            rows = tuple(
                (line.line_code, format(line.amount, "f"), line.source_type)
                for line in uow.cash_snapshots.lines(run.company_id, cash.id)
            )
            disclosures = uow.cash_snapshots.disclosures(run.company_id, cash.id)
            if disclosures:
                sections = (
                    (
                        "NonCashDisclosure",
                        ("source_type", "amount", "journal_id", "evidence_id"),
                        tuple(
                            (
                                item.source_type,
                                format(item.amount, "f"),
                                str(item.journal_id),
                                str(item.evidence_id),
                            )
                            for item in disclosures
                        ),
                    ),
                )
            metadata += (
                ("cash_flow_snapshot_id", str(cash.id)),
                ("cash_flow_snapshot_version", str(cash.close_version)),
                ("cash_flow_snapshot_generated_at", cash.generated_at.isoformat()),
                ("cash_flow_validation", "INTERNAL_VALIDATION_ONLY"),
            )
        elif run.report_code == "FINANCIAL_METRICS":
            values = {
                line.line_code: line.current_amount
                for view in (balance, income)
                for line in view.lines
            }
            rows = tuple(
                (
                    item.metric_code,
                    str(item.formula_version),
                    item.numerator_line_code,
                    format(item.numerator, "f"),
                    item.denominator_line_code,
                    format(item.denominator, "f"),
                    format(item.value, "f") if item.value is not None else "",
                    item.status,
                )
                for item in calculate(values)
            )
            columns = (
                "metric_code",
                "formula_version",
                "numerator_code",
                "numerator",
                "denominator_code",
                "denominator",
                "value",
                "status",
            )
        else:
            view = balance if run.report_code == "BALANCE_SHEET" else income
            columns = ("line_code", "label", "amount")
            rows = tuple(
                (line.line_code, line.label, format(line.current_amount, "f"))
                for line in view.lines
            )
        return ReportDocument(metadata, columns, rows, sections)


class _GenerationFailed(Exception):
    """Failure code is recorded on the run after rolling back the generating transaction."""
