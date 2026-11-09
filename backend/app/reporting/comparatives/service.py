"""동결된 BS/IS 원천을 기존 재무제표 Snapshot/Line에 투영합니다."""

import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.accounting.periods.domain.entities import Period
from app.closing.application.service import ClosingService
from app.closing.domain.entities import ClosingRun
from app.closing.domain.errors import ClosingRunStale
from app.companies.application.service import require_company
from app.contracts.access_errors import (
    InvalidInput,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.comparatives.models import (
    ComparativeReclassificationModel,
    ComparativeStatementAuditModel,
    ComparativeStatementModel,
)
from app.reporting.financial_statements.domain.entities import StatementSet, StatementView
from app.reporting.financial_statements.domain.rules import ReportSourceStale
from app.reporting.financial_statements.infrastructure.models import (
    ReportLineModel,
    StatementLineModel,
    StatementModel,
    StatementSnapshotModel,
)

KINDS = ("BALANCE_SHEET", "INCOME_STATEMENT")
ZERO = Decimal("0")


class ComparativeStatementsService:
    def __init__(self, factory: Callable[[], CashFlowUnitOfWork]) -> None:
        self.factory = factory

    @staticmethod
    def _record(row: ComparativeStatementModel) -> dict[str, object]:
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    def _sources(
        self, uow: CashFlowUnitOfWork, company: UUID, current_id: UUID, prior_id: UUID
    ) -> tuple[
        Period,
        ClosingRun,
        StatementSet,
        dict[str, StatementView | None],
        Period,
        ClosingRun,
        StatementSet,
        dict[str, StatementView | None],
        str,
    ]:
        current_period, current_run, current_tb, _, _ = ClosingService.closed_adjusted_source(
            uow, company, current_id
        )
        prior_period, prior_run, prior_tb, _, _ = ClosingService.closed_adjusted_source(
            uow, company, prior_id
        )
        if current_period.end_date <= prior_period.end_date:
            raise InvalidInput()
        current_days = (current_period.end_date - current_period.start_date).days
        prior_days = (prior_period.end_date - prior_period.start_date).days
        if abs(current_days - prior_days) > 1:
            raise InvalidInput()
        current_sets = uow.statements.sets(company, current_id)
        prior_sets = uow.statements.sets(company, prior_id)
        current_set = next(
            (row for row in current_sets if row.close_version == current_period.close_version), None
        )
        prior_set = next(
            (row for row in prior_sets if row.close_version == prior_period.close_version), None
        )
        if (
            current_set is None
            or prior_set is None
            or current_set.taxonomy_id != prior_set.taxonomy_id
        ):
            raise StateConflict()
        for statement_set, period, trial_digest in (
            (current_set, current_period, current_tb),
            (prior_set, prior_period, prior_tb),
        ):
            mappings = uow.statements.mappings(company, statement_set.taxonomy_id, period.end_date)
            if (
                statement_set.trial_balance_digest != trial_digest
                or statement_set.mapping_digest
                != digest([(str(account), code, version) for account, code, version in mappings])
            ):
                raise ReportSourceStale()
        current_views = {
            kind: uow.statements.statement(company, current_set.id, kind) for kind in KINDS
        }
        prior_views = {
            kind: uow.statements.statement(company, prior_set.id, kind) for kind in KINDS
        }
        if any(current_views[k] is None or prior_views[k] is None for k in KINDS):
            raise StateConflict()
        current_views = {kind: view for kind, view in current_views.items() if view is not None}
        prior_views = {kind: view for kind, view in prior_views.items() if view is not None}
        current_bs = current_views["BALANCE_SHEET"]
        current_is = current_views["INCOME_STATEMENT"]
        prior_bs = prior_views["BALANCE_SHEET"]
        prior_is = prior_views["INCOME_STATEMENT"]
        assert current_bs is not None and current_is is not None
        assert prior_bs is not None and prior_is is not None
        for kind in KINDS:
            current_view = current_views[kind]
            prior_view = prior_views[kind]
            assert current_view is not None and prior_view is not None
            current_codes = {line.line_code for line in current_view.lines}
            prior_codes = {line.line_code for line in prior_view.lines}
            if current_codes != prior_codes:
                raise StateConflict()
        source = digest(
            {
                "current": [
                    current_set.id,
                    current_set.close_version,
                    current_tb,
                    current_set.mapping_digest,
                    current_set.taxonomy_version,
                    current_bs.snapshot_digest,
                    current_is.snapshot_digest,
                ],
                "prior": [
                    prior_set.id,
                    prior_set.close_version,
                    prior_tb,
                    prior_set.mapping_digest,
                    prior_set.taxonomy_version,
                    prior_bs.snapshot_digest,
                    prior_is.snapshot_digest,
                ],
            }
        )
        return (
            current_period,
            current_run,
            current_set,
            current_views,
            prior_period,
            prior_run,
            prior_set,
            prior_views,
            source,
        )

    def readiness(
        self, actor: Principal, company: UUID, period_id: UUID, comparison_period_id: UUID
    ) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            try:
                values = self._sources(uow, company, period_id, comparison_period_id)
            except (ClosingRunStale, ReportSourceStale, StateConflict, InvalidInput):
                return {
                    "status": "BLOCKED",
                    "reasons": ["SOURCE_NOT_COMPARABLE"],
                    "supported_statements": list(KINDS),
                    "unsupported_statements": ["CASH_FLOW", "CHANGES_IN_EQUITY", "NOTES"],
                }
            return {
                "status": "READY",
                "reasons": [],
                "source_digest": values[-1],
                "supported_statements": list(KINDS),
                "unsupported_statements": ["CASH_FLOW", "CHANGES_IN_EQUITY", "NOTES"],
            }

    def generate(
        self,
        actor: Principal,
        company: UUID,
        period_id: UUID,
        comparison_period_id: UUID,
        key: str,
    ) -> dict[str, object]:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            (
                current_period,
                current_run,
                current_set,
                current_views,
                prior_period,
                prior_run,
                prior_set,
                prior_views,
                source,
            ) = self._sources(uow, company, period_id, comparison_period_id)
            command_code = "financial_statement.compare"
            fingerprint = digest((str(period_id), str(comparison_period_id), source))
            uow.lock_command(company, actor.user_id, command_code, key)
            replayed_set_id = uow.statements.replay(
                company, actor.user_id, key, fingerprint, command_code
            )
            if replayed_set_id is not None:
                replayed = uow.session.scalar(
                    select(ComparativeStatementModel)
                    .where(
                        ComparativeStatementModel.company_id == company,
                        ComparativeStatementModel.period_id == period_id,
                        ComparativeStatementModel.comparison_period_id == comparison_period_id,
                        ComparativeStatementModel.source_digest == source,
                    )
                    .order_by(ComparativeStatementModel.revision.desc())
                    .limit(1)
                )
                if replayed is None:
                    raise ResourceNotFound()
                return self._record(replayed)
            prior_same = uow.session.scalar(
                select(ComparativeStatementModel)
                .where(
                    ComparativeStatementModel.company_id == company,
                    ComparativeStatementModel.period_id == period_id,
                    ComparativeStatementModel.comparison_period_id == comparison_period_id,
                    ComparativeStatementModel.source_digest == source,
                    ComparativeStatementModel.status != "SUPERSEDED",
                )
                .order_by(ComparativeStatementModel.revision.desc())
                .limit(1)
            )
            if prior_same is not None:
                uow.statements.record(
                    company,
                    actor.user_id,
                    key,
                    fingerprint,
                    current_set.id,
                    uow.now(),
                    command_code,
                )
                return self._record(prior_same)
            revision = (
                uow.session.scalar(
                    select(func.max(ComparativeStatementModel.revision)).where(
                        ComparativeStatementModel.company_id == company,
                        ComparativeStatementModel.period_id == period_id,
                        ComparativeStatementModel.comparison_period_id == comparison_period_id,
                    )
                )
                or 0
            ) + 1
            row = ComparativeStatementModel(
                id=uuid4(),
                company_id=company,
                period_id=period_id,
                comparison_period_id=comparison_period_id,
                statement_set_id=current_set.id,
                comparison_statement_set_id=prior_set.id,
                close_version=current_period.close_version,
                comparison_close_version=prior_period.close_version,
                current_source_digest=current_set.trial_balance_digest,
                comparison_source_digest=prior_set.trial_balance_digest,
                current_mapping_digest=current_set.mapping_digest,
                comparison_mapping_digest=prior_set.mapping_digest,
                taxonomy_version=current_set.taxonomy_version,
                source_digest=source,
                revision=revision,
                status="DRAFT",
                created_by=actor.user_id,
                reviewer_id=None,
                review_digest=None,
                approved_at=None,
                version=1,
            )
            uow.session.add(row)
            uow.session.flush()
            for kind in KINDS:
                current_statement = uow.session.scalar(
                    select(StatementModel).where(
                        StatementModel.company_id == company,
                        StatementModel.statement_set_id == current_set.id,
                        StatementModel.statement_type == kind,
                    )
                )
                assert current_statement is not None
                original_snapshot = uow.session.scalar(
                    select(StatementSnapshotModel)
                    .where(
                        StatementSnapshotModel.company_id == company,
                        StatementSnapshotModel.statement_id == current_statement.id,
                        StatementSnapshotModel.comparative_statement_id.is_(None),
                    )
                    .order_by(StatementSnapshotModel.statement_version.desc())
                    .limit(1)
                )
                assert original_snapshot is not None
                version = (
                    uow.session.scalar(
                        select(func.max(StatementSnapshotModel.statement_version)).where(
                            StatementSnapshotModel.company_id == company,
                            StatementSnapshotModel.statement_id == current_statement.id,
                        )
                    )
                    or 0
                ) + 1
                snapshot_id = uuid4()
                uow.session.add(
                    StatementSnapshotModel(
                        id=snapshot_id,
                        company_id=company,
                        statement_id=current_statement.id,
                        comparative_statement_id=row.id,
                        statement_version=version,
                        source_digest=source,
                        mapping_digest=digest(
                            [current_set.mapping_digest, prior_set.mapping_digest]
                        ),
                        generated_at=datetime.now(UTC),
                    )
                )
                uow.session.flush()
                current_view = current_views[kind]
                prior_view = prior_views[kind]
                assert current_view is not None and prior_view is not None
                current_lines = {line.line_code: line for line in current_view.lines}
                prior_lines = {line.line_code: line for line in prior_view.lines}
                line_records = uow.session.execute(
                    select(StatementLineModel, ReportLineModel)
                    .join(ReportLineModel, ReportLineModel.id == StatementLineModel.report_line_id)
                    .where(
                        StatementLineModel.company_id == company,
                        StatementLineModel.snapshot_id == original_snapshot.id,
                    )
                ).all()
                for line, report in line_records:
                    current_line = current_lines[report.line_code]
                    prior_line = prior_lines[report.line_code]
                    uow.session.add(
                        StatementLineModel(
                            id=uuid4(),
                            company_id=company,
                            snapshot_id=snapshot_id,
                            report_line_id=line.report_line_id,
                            current_amount=current_line.current_amount,
                            prior_amount=prior_line.current_amount,
                            presentation_amount=prior_line.current_amount,
                            current_source_line_id=current_line.id,
                            prior_source_line_id=prior_line.id,
                            source_digest=source,
                        )
                    )
            uow.session.add(
                ComparativeStatementAuditModel(
                    id=uuid4(),
                    company_id=company,
                    comparative_statement_id=row.id,
                    actor_id=actor.user_id,
                    action="GENERATED",
                    reason=None,
                    from_status=None,
                    to_status="DRAFT",
                    expected_version=1,
                    created_at=datetime.now(UTC),
                )
            )
            uow.statements.record(
                company,
                actor.user_id,
                key,
                fingerprint,
                current_set.id,
                uow.now(),
                command_code,
            )
            return self._record(row)

    def list(self, actor: Principal, company: UUID, period_id: UUID) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return [
                self._record(row)
                for row in uow.session.scalars(
                    select(ComparativeStatementModel)
                    .where(
                        ComparativeStatementModel.company_id == company,
                        ComparativeStatementModel.period_id == period_id,
                    )
                    .order_by(ComparativeStatementModel.revision.desc())
                )
            ]

    def detail(self, actor: Principal, company: UUID, snapshot_id: UUID) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            row = uow.session.scalar(
                select(ComparativeStatementModel).where(
                    ComparativeStatementModel.company_id == company,
                    ComparativeStatementModel.id == snapshot_id,
                )
            )
            if row is None:
                raise ResourceNotFound()
            result = self._record(row)
            result["mapping_changed"] = row.current_mapping_digest != row.comparison_mapping_digest
            try:
                current_sources = self._sources(
                    uow, company, row.period_id, row.comparison_period_id
                )
                result["source_current"] = current_sources[-1] == row.source_digest
            except (ClosingRunStale, ReportSourceStale, StateConflict, InvalidInput):
                result["source_current"] = False
            snapshots = list(
                uow.session.scalars(
                    select(StatementSnapshotModel).where(
                        StatementSnapshotModel.company_id == company,
                        StatementSnapshotModel.comparative_statement_id == row.id,
                    )
                )
            )
            statements = {}
            for snapshot in snapshots:
                statement = uow.session.get(StatementModel, snapshot.statement_id)
                assert statement is not None
                lines = uow.session.execute(
                    select(StatementLineModel, ReportLineModel)
                    .join(ReportLineModel, ReportLineModel.id == StatementLineModel.report_line_id)
                    .where(
                        StatementLineModel.company_id == company,
                        StatementLineModel.snapshot_id == snapshot.id,
                    )
                    .order_by(ReportLineModel.display_order)
                ).all()
                statements[statement.statement_type] = [
                    {
                        "line_code": report.line_code,
                        "label": report.label,
                        "current_amount": line.current_amount,
                        "prior_amount": line.prior_amount,
                        "presentation_amount": line.presentation_amount,
                        "variance": line.current_amount - line.presentation_amount,
                        "current_source_line_id": line.current_source_line_id,
                        "prior_source_line_id": line.prior_source_line_id,
                    }
                    for line, report in lines
                ]
            result["statements"] = statements
            result["reclassifications"] = [
                {column.name: getattr(item, column.name) for column in item.__table__.columns}
                for item in uow.session.scalars(
                    select(ComparativeReclassificationModel).where(
                        ComparativeReclassificationModel.company_id == company,
                        ComparativeReclassificationModel.comparative_statement_id == row.id,
                    )
                )
            ]
            return result

    def sources(
        self,
        actor: Principal,
        company: UUID,
        snapshot_id: UUID,
        statement_type: str,
        line_code: str,
    ) -> dict[str, object]:
        if statement_type not in KINDS:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            row = uow.session.scalar(
                select(ComparativeStatementModel).where(
                    ComparativeStatementModel.company_id == company,
                    ComparativeStatementModel.id == snapshot_id,
                )
            )
            if row is None:
                raise ResourceNotFound()
            line = uow.session.execute(
                select(StatementLineModel)
                .join(
                    StatementSnapshotModel,
                    StatementSnapshotModel.id == StatementLineModel.snapshot_id,
                )
                .join(StatementModel, StatementModel.id == StatementSnapshotModel.statement_id)
                .join(ReportLineModel, ReportLineModel.id == StatementLineModel.report_line_id)
                .where(
                    StatementSnapshotModel.company_id == company,
                    StatementSnapshotModel.comparative_statement_id == row.id,
                    StatementModel.statement_type == statement_type,
                    ReportLineModel.line_code == line_code,
                )
            ).scalar_one_or_none()
            if line is None:
                raise ResourceNotFound()
            assert line.current_source_line_id is not None
            assert line.prior_source_line_id is not None
            return {
                "current": [
                    asdict(source)
                    for source in uow.statements.sources(company, line.current_source_line_id)
                ],
                "prior": [
                    asdict(source)
                    for source in uow.statements.sources(company, line.prior_source_line_id)
                ],
            }

    def reclassify(
        self,
        actor: Principal,
        company: UUID,
        snapshot_id: UUID,
        *,
        statement_type: str,
        from_line_code: str,
        to_line_code: str,
        amount: Decimal,
        reason: str,
        expected_version: int,
    ) -> dict[str, object]:
        if (
            amount <= ZERO
            or not reason.strip()
            or statement_type not in KINDS
            or from_line_code == to_line_code
        ):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            row = uow.session.scalar(
                select(ComparativeStatementModel)
                .where(
                    ComparativeStatementModel.company_id == company,
                    ComparativeStatementModel.id == snapshot_id,
                )
                .with_for_update()
            )
            if row is None:
                raise ResourceNotFound()
            if row.version != expected_version:
                raise VersionConflict()
            if row.status != "DRAFT":
                raise StateConflict()
            snapshot = uow.session.scalar(
                select(StatementSnapshotModel)
                .join(StatementModel, StatementModel.id == StatementSnapshotModel.statement_id)
                .where(
                    StatementSnapshotModel.company_id == company,
                    StatementSnapshotModel.comparative_statement_id == row.id,
                    StatementModel.statement_type == statement_type,
                )
            )
            assert snapshot is not None
            joined = uow.session.execute(
                select(StatementLineModel, ReportLineModel)
                .join(ReportLineModel, ReportLineModel.id == StatementLineModel.report_line_id)
                .where(
                    StatementLineModel.company_id == company,
                    StatementLineModel.snapshot_id == snapshot.id,
                )
                .with_for_update()
            ).all()
            by_code = {report.line_code: line for line, report in joined}
            source, target = by_code.get(from_line_code), by_code.get(to_line_code)
            if source is None or target is None:
                raise InvalidInput()
            source_report = next(report for line, report in joined if line.id == source.id)
            target_report = next(report for line, report in joined if line.id == target.id)
            if (
                source_report.subtotal_type != "LEAF"
                or target_report.subtotal_type != "LEAF"
                or source_report.normal_sign != target_report.normal_sign
            ):
                raise InvalidInput()
            if source.presentation_amount is None or source.presentation_amount < amount:
                raise InvalidInput()
            source.presentation_amount -= amount
            target.presentation_amount += amount
            raw_values = {code: item.presentation_amount for code, item in by_code.items()}
            if any(value is None for value in raw_values.values()):
                raise StateConflict()
            values = {code: cast(Decimal, value) for code, value in raw_values.items()}
            if statement_type == "INCOME_STATEMENT":
                values["GROSS_PROFIT"] = values["REVENUE"] - values["COGS"]
                values["OPERATING_PROFIT"] = values["GROSS_PROFIT"] - values["OPERATING_EXPENSE"]
                values["PROFIT_BEFORE_TAX"] = (
                    values["OPERATING_PROFIT"]
                    + values["NON_OPERATING_INCOME"]
                    - values["NON_OPERATING_EXPENSE"]
                )
                values["NET_PROFIT"] = values["PROFIT_BEFORE_TAX"] - values["TAX_EXPENSE"]
                for code in ("GROSS_PROFIT", "OPERATING_PROFIT", "PROFIT_BEFORE_TAX", "NET_PROFIT"):
                    by_code[code].presentation_amount = values[code]
            else:
                values["ASSETS"] = values["ASSET_ACCOUNTS"]
                values["LIABILITIES"] = values["LIABILITY_ACCOUNTS"]
                values["EQUITY"] = values["EQUITY_ACCOUNTS"] + values["UNTRANSFERRED_PROFIT"]
                values["LIABILITIES_EQUITY"] = values["LIABILITIES"] + values["EQUITY"]
                for code in ("ASSETS", "LIABILITIES", "EQUITY", "LIABILITIES_EQUITY"):
                    by_code[code].presentation_amount = values[code]
            uow.session.add(
                ComparativeReclassificationModel(
                    id=uuid4(),
                    company_id=company,
                    comparative_statement_id=row.id,
                    statement_type=statement_type,
                    from_line_code=from_line_code,
                    to_line_code=to_line_code,
                    amount=amount,
                    reason=reason.strip(),
                    created_by=actor.user_id,
                    created_at=datetime.now(UTC),
                )
            )
            old = row.status
            row.version += 1
            uow.session.add(
                ComparativeStatementAuditModel(
                    id=uuid4(),
                    company_id=company,
                    comparative_statement_id=row.id,
                    actor_id=actor.user_id,
                    action="RECLASSIFIED",
                    reason=reason.strip(),
                    from_status=old,
                    to_status=old,
                    expected_version=expected_version,
                    created_at=datetime.now(UTC),
                )
            )
            return self._record(row)

    def request_review(
        self, actor: Principal, company: UUID, snapshot_id: UUID, expected_version: int
    ) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            row = self._locked(uow, company, snapshot_id, expected_version, "DRAFT")
            fresh = self._sources(uow, company, row.period_id, row.comparison_period_id)
            if fresh[-1] != row.source_digest:
                raise ReportSourceStale()
            source = self._review_digest(uow, company, row)
            row.review_digest = source
            self._transition(
                uow, row, actor.user_id, expected_version, "REVIEW_REQUESTED", "REVIEW_REQUESTED"
            )
            return self._record(row)

    def approve(
        self, actor: Principal, company: UUID, snapshot_id: UUID, expected_version: int
    ) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.approve")
            row = self._locked(uow, company, snapshot_id, expected_version, "REVIEW_REQUESTED")
            if row.created_by == actor.user_id or row.review_digest != self._review_digest(
                uow, company, row
            ):
                raise StateConflict()
            fresh = self._sources(uow, company, row.period_id, row.comparison_period_id)
            if fresh[-1] != row.source_digest:
                raise ReportSourceStale()
            row.reviewer_id = actor.user_id
            row.approved_at = datetime.now(UTC)
            self._transition(uow, row, actor.user_id, expected_version, "APPROVED", "APPROVED")
            return self._record(row)

    def reject(
        self, actor: Principal, company: UUID, snapshot_id: UUID, expected_version: int, reason: str
    ) -> dict[str, object]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.approve")
            row = self._locked(uow, company, snapshot_id, expected_version, "REVIEW_REQUESTED")
            if row.created_by == actor.user_id or not reason.strip():
                raise StateConflict()
            row.reviewer_id = actor.user_id
            self._transition(uow, row, actor.user_id, expected_version, "REJECTED", reason.strip())
            return self._record(row)

    @staticmethod
    def _locked(
        uow: CashFlowUnitOfWork,
        company: UUID,
        snapshot_id: UUID,
        expected_version: int,
        status: str,
    ) -> ComparativeStatementModel:
        row = uow.session.scalar(
            select(ComparativeStatementModel)
            .where(
                ComparativeStatementModel.company_id == company,
                ComparativeStatementModel.id == snapshot_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ResourceNotFound()
        if row.version != expected_version:
            raise VersionConflict()
        if row.status != status:
            raise StateConflict()
        return row

    @staticmethod
    def _transition(
        uow: CashFlowUnitOfWork,
        row: ComparativeStatementModel,
        actor: UUID,
        expected_version: int,
        status: str,
        reason: str,
    ) -> None:
        old = row.status
        row.status = status
        row.version += 1
        uow.session.add(
            ComparativeStatementAuditModel(
                id=uuid4(),
                company_id=row.company_id,
                comparative_statement_id=row.id,
                actor_id=actor,
                action=status,
                reason=reason,
                from_status=old,
                to_status=status,
                expected_version=expected_version,
                created_at=datetime.now(UTC),
            )
        )

    @staticmethod
    def _review_digest(
        uow: CashFlowUnitOfWork, company: UUID, row: ComparativeStatementModel
    ) -> str:
        lines = uow.session.execute(
            select(
                StatementLineModel.snapshot_id,
                StatementLineModel.report_line_id,
                StatementLineModel.current_amount,
                StatementLineModel.prior_amount,
                StatementLineModel.presentation_amount,
                StatementLineModel.current_source_line_id,
                StatementLineModel.prior_source_line_id,
            )
            .join(
                StatementSnapshotModel, StatementSnapshotModel.id == StatementLineModel.snapshot_id
            )
            .where(
                StatementSnapshotModel.company_id == company,
                StatementSnapshotModel.comparative_statement_id == row.id,
            )
            .order_by(StatementLineModel.snapshot_id, StatementLineModel.report_line_id)
        ).all()
        reclasses = uow.session.scalars(
            select(ComparativeReclassificationModel)
            .where(
                ComparativeReclassificationModel.company_id == company,
                ComparativeReclassificationModel.comparative_statement_id == row.id,
            )
            .order_by(ComparativeReclassificationModel.created_at)
        ).all()
        return digest(
            {
                "source": row.source_digest,
                "lines": [[str(value) for value in line] for line in lines],
                "reclassifications": [
                    {
                        "type": r.statement_type,
                        "from": r.from_line_code,
                        "to": r.to_line_code,
                        "amount": str(r.amount),
                        "reason": r.reason,
                    }
                    for r in reclasses
                ],
            }
        )
