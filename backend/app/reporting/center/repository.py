"""Company-scoped relational report run persistence."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.access_errors import StateConflict
from app.reporting.center.models import ReportRunModel


@dataclass(frozen=True)
class ReportRun:
    id: UUID
    company_id: UUID
    report_code: str
    format: str
    period_preset: str
    period_mode: str
    date_from: date | None
    date_to: date | None
    as_of: date | None
    period_id: UUID
    statement_set_id: UUID
    close_version: int
    taxonomy_version: int
    trial_balance_digest: str
    mapping_digest: str
    balance_sheet_digest: str
    income_statement_digest: str
    source_digest: str
    template_version: int
    status: str
    requested_by: UUID
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    retry_of_run_id: UUID | None
    version: int


def read_run(row: ReportRunModel) -> ReportRun:
    return ReportRun(**{name: getattr(row, name) for name in ReportRun.__dataclass_fields__})


class ReportRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, value: ReportRun, key: str, fingerprint: str) -> None:
        fields = {name: getattr(value, name) for name in ReportRun.__dataclass_fields__}
        self.session.add(ReportRunModel(**fields, idempotency_key=key, request_digest=fingerprint))
        self.session.flush()

    def replay(self, company: UUID, actor: UUID, key: str, fingerprint: str) -> ReportRun | None:
        row = self.session.scalar(
            select(ReportRunModel).where(
                ReportRunModel.company_id == company,
                ReportRunModel.requested_by == actor,
                ReportRunModel.idempotency_key == key,
            )
        )
        if row is not None and row.request_digest != fingerprint:
            raise StateConflict()
        return read_run(row) if row else None

    def get(self, company: UUID, run_id: UUID, *, lock: bool = False) -> ReportRun | None:
        query = select(ReportRunModel).where(
            ReportRunModel.company_id == company, ReportRunModel.id == run_id
        )
        if lock:
            query = query.with_for_update()
        row = self.session.scalar(query)
        return read_run(row) if row else None

    def list(self, company: UUID, limit: int = 50) -> list[ReportRun]:
        return [
            read_run(row)
            for row in self.session.scalars(
                select(ReportRunModel)
                .where(ReportRunModel.company_id == company)
                .order_by(ReportRunModel.requested_at.desc(), ReportRunModel.id.desc())
                .limit(limit)
            )
        ]
