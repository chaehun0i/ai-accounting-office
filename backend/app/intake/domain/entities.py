from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.intake.domain.canonical_fields import Mapping, SourceType, TargetContext


@dataclass(frozen=True)
class Import:
    id: UUID
    company_id: UUID
    requested_by: UUID
    storage_object_id: UUID
    storage_key: str
    source_type: SourceType
    target_context: TargetContext
    source_system: str
    original_filename: str
    content_type: str
    file_sha256: str
    status: str
    version: int
    mapping_version: int
    preview_digest: str | None
    preview_expires_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class Receipt:
    id: UUID
    company_id: UUID
    import_id: UUID
    source_digest: str
    transaction_count: int
    evidence_count: int
    counterparty_count: int
    status: str
    created_at: datetime


@dataclass(frozen=True)
class Confirmation:
    fingerprint: str
    receipt: Receipt


@dataclass(frozen=True)
class Column:
    sheet_index: int
    sheet_name: str
    column_index: int
    source_header: str
    mapping: Mapping
