"""Company-scoped relational report run persistence."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.access_errors import StateConflict
from app.reporting.center.models import ReportArtifactModel, ReportRunModel
from app.storage.infrastructure.models import StorageObjectModel


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


@dataclass(frozen=True)
class ReportArtifact:
    id: UUID
    company_id: UUID
    run_id: UUID
    storage_key: str
    file_name: str
    file_sha256: str
    size_bytes: int
    content_type: str
    created_at: datetime


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

    def artifact(self, company: UUID, run_id: UUID) -> ReportArtifact | None:
        record = self.session.execute(
            select(ReportArtifactModel, StorageObjectModel)
            .join(
                StorageObjectModel,
                (StorageObjectModel.id == ReportArtifactModel.storage_object_id)
                & (StorageObjectModel.company_id == company)
                & (StorageObjectModel.sha256 == ReportArtifactModel.file_sha256),
            )
            .where(
                ReportArtifactModel.company_id == company,
                ReportArtifactModel.run_id == run_id,
                StorageObjectModel.status == "AVAILABLE",
            )
        ).one_or_none()
        if record is None:
            return None
        row, stored = record
        return ReportArtifact(
            row.id,
            company,
            run_id,
            stored.storage_key,
            row.file_name,
            row.file_sha256,
            row.size_bytes,
            stored.content_type,
            row.created_at,
        )

    def mark_started(self, company: UUID, run_id: UUID, now: datetime) -> None:
        row = self._locked(company, run_id)
        row.status = "GENERATING"
        row.started_at = now
        row.version += 1

    def complete(
        self,
        run: ReportRun,
        *,
        storage_key: str,
        file_name: str,
        file_sha256: str,
        size_bytes: int,
        content_type: str,
        now: datetime,
    ) -> None:
        row = self._locked(run.company_id, run.id)
        if row.status != "GENERATING" or self.artifact(run.company_id, run.id) is not None:
            raise StateConflict()
        storage_id = uuid4()
        artifact_id = uuid4()
        self.session.add(
            StorageObjectModel(
                id=storage_id,
                company_id=run.company_id,
                storage_provider="LOCAL",
                storage_key=storage_key,
                original_filename=file_name,
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=file_sha256,
                status="AVAILABLE",
                created_by=run.requested_by,
                created_at=now,
            )
        )
        self.session.flush()
        self.session.add(
            ReportArtifactModel(
                id=artifact_id,
                company_id=run.company_id,
                run_id=run.id,
                storage_object_id=storage_id,
                file_name=file_name,
                file_sha256=file_sha256,
                size_bytes=size_bytes,
                created_at=now,
                expires_at=None,
            )
        )
        row.status = "COMPLETED"
        row.completed_at = now
        row.error_code = None
        row.version += 1
        self.session.flush()

    def fail(self, company: UUID, run_id: UUID, code: str, now: datetime) -> None:
        row = self._locked(company, run_id)
        if row.status == "COMPLETED":
            return
        row.status = "FAILED"
        row.started_at = row.started_at or now
        row.error_code = code
        row.completed_at = now
        row.version += 1

    def _locked(self, company: UUID, run_id: UUID) -> ReportRunModel:
        row = self.session.scalar(
            select(ReportRunModel)
            .where(ReportRunModel.company_id == company, ReportRunModel.id == run_id)
            .with_for_update()
        )
        if row is None:
            raise StateConflict()
        return row
