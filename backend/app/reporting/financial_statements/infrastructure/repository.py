"""보고서 원천은 회사 범위로 읽고 스냅샷은 추가만 합니다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting.accounts.infrastructure.models import AccountModel
from app.accounting.journals.infrastructure.models import JournalLineModel, JournalModel
from app.reporting.financial_statements.domain.entities import (
    SourceLine,
    StatementLine,
    StatementSet,
    StatementView,
)
from app.reporting.financial_statements.domain.rules import ReportIdempotencyConflict
from app.reporting.financial_statements.infrastructure.models import (
    ReportAccountMappingModel,
    ReportLineModel,
    ReportTaxonomyModel,
    StatementCommandModel,
    StatementLineModel,
    StatementModel,
    StatementSetModel,
    StatementSnapshotModel,
    StatementSourceModel,
)


class StatementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def active_taxonomy(self, as_of: date) -> tuple[UUID, int] | None:
        row = self.session.scalar(
            select(ReportTaxonomyModel)
            .where(
                ReportTaxonomyModel.status == "ACTIVE",
                ReportTaxonomyModel.effective_from <= as_of,
                (ReportTaxonomyModel.effective_to.is_(None))
                | (ReportTaxonomyModel.effective_to >= as_of),
            )
            .order_by(ReportTaxonomyModel.version.desc())
            .limit(1)
        )
        return (row.id, row.version) if row else None

    def line_ids(self, taxonomy: UUID) -> dict[str, UUID]:
        return {
            row.line_code: row.id
            for row in self.session.scalars(
                select(ReportLineModel).where(ReportLineModel.taxonomy_id == taxonomy)
            )
        }

    def mappings(self, company: UUID, taxonomy: UUID, as_of: date) -> list[tuple[UUID, str, int]]:
        query = (
            select(
                ReportAccountMappingModel.account_id,
                ReportLineModel.line_code,
                ReportAccountMappingModel.version,
            )
            .join(ReportLineModel, ReportLineModel.id == ReportAccountMappingModel.report_line_id)
            .where(
                ReportAccountMappingModel.company_id == company,
                ReportAccountMappingModel.taxonomy_id == taxonomy,
                ReportAccountMappingModel.effective_from <= as_of,
                (ReportAccountMappingModel.effective_to.is_(None))
                | (ReportAccountMappingModel.effective_to >= as_of),
            )
            .order_by(ReportAccountMappingModel.account_id)
        )
        return [(account, code, version) for account, code, version in self.session.execute(query)]

    def add_mapping(
        self, company: UUID, taxonomy: UUID, account: UUID, line: UUID, effective_from: date
    ) -> None:
        self.session.add(
            ReportAccountMappingModel(
                id=uuid4(),
                company_id=company,
                taxonomy_id=taxonomy,
                account_id=account,
                report_line_id=line,
                effective_from=effective_from,
                effective_to=None,
                version=1,
            )
        )
        self.session.flush()

    def _set(self, row: StatementSetModel) -> StatementSet:
        taxonomy = self.session.get(ReportTaxonomyModel, row.taxonomy_id)
        assert taxonomy is not None
        return StatementSet(
            id=row.id,
            company_id=row.company_id,
            period_id=row.period_id,
            closing_run_id=row.closing_run_id,
            close_version=row.close_version,
            taxonomy_id=row.taxonomy_id,
            taxonomy_version=taxonomy.version,
            status=row.status,
            trial_balance_digest=row.trial_balance_digest,
            mapping_digest=row.mapping_digest,
            generated_at=row.generated_at,
        )

    def set_for_source(
        self,
        company: UUID,
        period: UUID,
        close_version: int,
        taxonomy: UUID,
        source: str,
        mapping: str,
    ) -> StatementSet | None:
        row = self.session.scalar(
            select(StatementSetModel).where(
                StatementSetModel.company_id == company,
                StatementSetModel.period_id == period,
                StatementSetModel.close_version == close_version,
                StatementSetModel.taxonomy_id == taxonomy,
                StatementSetModel.trial_balance_digest == source,
                StatementSetModel.mapping_digest == mapping,
            )
        )
        return self._set(row) if row else None

    def set(self, company: UUID, identifier: UUID) -> StatementSet | None:
        row = self.session.scalar(
            select(StatementSetModel).where(
                StatementSetModel.company_id == company, StatementSetModel.id == identifier
            )
        )
        return self._set(row) if row else None

    def sets(self, company: UUID, period: UUID) -> list[StatementSet]:
        return [
            self._set(row)
            for row in self.session.scalars(
                select(StatementSetModel)
                .where(
                    StatementSetModel.company_id == company, StatementSetModel.period_id == period
                )
                .order_by(
                    StatementSetModel.close_version.desc(), StatementSetModel.generated_at.desc()
                )
            )
        ]

    def statement(self, company: UUID, set_id: UUID, kind: str) -> StatementView | None:
        row = self.session.scalar(
            select(StatementModel).where(
                StatementModel.company_id == company,
                StatementModel.statement_set_id == set_id,
                StatementModel.statement_type == kind,
            )
        )
        if row is None:
            return None
        snapshot = self.session.scalar(
            select(StatementSnapshotModel).where(
                StatementSnapshotModel.company_id == company,
                StatementSnapshotModel.statement_id == row.id,
            )
        )
        assert snapshot is not None
        query = (
            select(StatementLineModel, ReportLineModel, ReportLineModel.line_code)
            .join(ReportLineModel, ReportLineModel.id == StatementLineModel.report_line_id)
            .where(
                StatementLineModel.company_id == company,
                StatementLineModel.snapshot_id == snapshot.id,
            )
            .order_by(ReportLineModel.display_order)
        )
        records = list(self.session.execute(query))
        codes = {report.id: report.line_code for _, report, _ in records}
        lines = tuple(
            StatementLine(
                id=line.id,
                line_code=report.line_code,
                label=report.label,
                parent_code=codes.get(report.parent_line_id),
                display_order=report.display_order,
                subtotal_type=report.subtotal_type,
                current_amount=line.current_amount,
            )
            for line, report, _ in records
        )
        return StatementView(row.id, set_id, kind, row.status, row.snapshot_digest, lines)

    def sources(self, company: UUID, statement_line: UUID) -> tuple[SourceLine, ...]:
        query = (
            select(StatementSourceModel, AccountModel, JournalLineModel, JournalModel)
            .join(
                AccountModel,
                (AccountModel.id == StatementSourceModel.account_id)
                & (AccountModel.company_id == company),
            )
            .join(
                JournalLineModel,
                (JournalLineModel.id == StatementSourceModel.journal_line_id)
                & (JournalLineModel.company_id == company),
            )
            .join(
                JournalModel,
                (JournalModel.id == JournalLineModel.journal_entry_id)
                & (JournalModel.company_id == company),
            )
            .where(
                StatementSourceModel.company_id == company,
                StatementSourceModel.statement_line_id == statement_line,
            )
            .order_by(
                AccountModel.account_code,
                JournalModel.entry_date,
                JournalModel.id,
                JournalLineModel.line_no,
            )
        )
        return tuple(
            SourceLine(
                account_id=account.id,
                account_code=account.account_code,
                account_name=account.account_name,
                journal_id=journal.id,
                journal_line_id=journal_line.id,
                journal_no=journal.journal_no or "",
                entry_date=journal.entry_date.isoformat(),
                amount=source.amount,
            )
            for source, account, journal_line, journal in self.session.execute(query)
        )

    def replay(self, company: UUID, actor: UUID, key: str, fingerprint: str) -> UUID | None:
        row = self.session.scalar(
            select(StatementCommandModel).where(
                StatementCommandModel.company_id == company,
                StatementCommandModel.actor_id == actor,
                StatementCommandModel.command_code == "financial_statement.generate",
                StatementCommandModel.idempotency_key == key,
            )
        )
        if row is not None and row.fingerprint != fingerprint:
            raise ReportIdempotencyConflict()
        return row.statement_set_id if row else None

    def record(
        self,
        company: UUID,
        actor: UUID,
        key: str,
        fingerprint: str,
        statement_set: UUID,
        now: datetime,
    ) -> None:
        self.session.add(
            StatementCommandModel(
                id=uuid4(),
                company_id=company,
                actor_id=actor,
                command_code="financial_statement.generate",
                idempotency_key=key,
                fingerprint=fingerprint,
                statement_set_id=statement_set,
                created_at=now,
            )
        )

    def add_set(self, value: StatementSet, generated_by: UUID) -> None:
        self.session.add(
            StatementSetModel(
                id=value.id,
                company_id=value.company_id,
                period_id=value.period_id,
                closing_run_id=value.closing_run_id,
                close_version=value.close_version,
                taxonomy_id=value.taxonomy_id,
                status=value.status,
                trial_balance_digest=value.trial_balance_digest,
                mapping_digest=value.mapping_digest,
                generated_by=generated_by,
                generated_at=value.generated_at,
                version=1,
            )
        )
        self.session.flush()

    def add_statement(
        self,
        company: UUID,
        set_id: UUID,
        statement_id: UUID,
        kind: str,
        snapshot_id: UUID,
        snapshot_digest: str,
        source_digest: str,
        mapping_digest: str,
        now: datetime,
    ) -> None:
        self.session.add(
            StatementModel(
                id=statement_id,
                company_id=company,
                statement_set_id=set_id,
                statement_type=kind,
                status="GENERATED",
                snapshot_digest=snapshot_digest,
                generated_at=now,
            )
        )
        self.session.flush()
        self.session.add(
            StatementSnapshotModel(
                id=snapshot_id,
                company_id=company,
                statement_id=statement_id,
                statement_version=1,
                source_digest=source_digest,
                mapping_digest=mapping_digest,
                generated_at=now,
            )
        )
        self.session.flush()

    def add_line(
        self,
        company: UUID,
        snapshot_id: UUID,
        line_id: UUID,
        report_line_id: UUID,
        amount: Decimal,
        source_digest: str,
    ) -> None:
        self.session.add(
            StatementLineModel(
                id=line_id,
                company_id=company,
                snapshot_id=snapshot_id,
                report_line_id=report_line_id,
                current_amount=amount,
                source_digest=source_digest,
            )
        )
        self.session.flush()

    def add_source(
        self, company: UUID, line_id: UUID, account: UUID, journal_line: UUID, amount: Decimal
    ) -> None:
        self.session.add(
            StatementSourceModel(
                id=uuid4(),
                company_id=company,
                statement_line_id=line_id,
                account_id=account,
                journal_line_id=journal_line,
                amount=amount,
            )
        )
