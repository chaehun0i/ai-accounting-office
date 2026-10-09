from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evidence.domain.entities import Evidence
from app.evidence.domain.types import EvidenceType
from app.evidence.infrastructure.models import EvidenceModel


class EvidenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, company_id: UUID, resource_id: UUID) -> Evidence | None:
        row = self.session.scalar(
            select(EvidenceModel).where(
                EvidenceModel.company_id == company_id, EvidenceModel.id == resource_id
            )
        )
        if row is None:
            return None
        return Evidence(
            row.id,
            row.company_id,
            EvidenceType(row.evidence_type),
            row.source_type,
            row.source_system,
            row.source_id,
            row.storage_object_id,
            row.sha256,
            row.content_type,
            row.original_filename,
            row.observed_at,
            row.ingested_at,
            row.created_at,
            row.created_by,
            row.parent_evidence_id,
        )

    def add(self, value: Evidence) -> None:
        self.session.add(EvidenceModel(**asdict(value)))
        self.session.flush()
