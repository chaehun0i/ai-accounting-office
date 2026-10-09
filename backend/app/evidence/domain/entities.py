from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.evidence.domain.types import EvidenceType


@dataclass(frozen=True)
class Evidence:
    id: UUID
    company_id: UUID
    evidence_type: EvidenceType
    source_type: str
    source_system: str
    source_id: str
    storage_object_id: UUID
    sha256: str
    content_type: str
    original_filename: str
    observed_at: datetime
    ingested_at: datetime
    created_at: datetime
    created_by: UUID
    parent_evidence_id: UUID | None = None
