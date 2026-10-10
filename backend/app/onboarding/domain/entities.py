from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.onboarding.domain.validation import Issue
from app.onboarding.domain.values import Cell


@dataclass(frozen=True)
class Workspace:
    id: UUID
    company_id: UUID
    status: str
    version: int
    cells: list[Cell]


@dataclass(frozen=True)
class ImportLink:
    import_id: UUID
    session_id: UUID
    status: str
    template_code: str
    template_version: str


@dataclass(frozen=True)
class MergeItem:
    incoming: Cell
    current: Cell | None
    classification: str


@dataclass(frozen=True)
class MergePreview:
    import_id: UUID
    session_version: int
    digest: str
    expires_at: datetime
    items: list[MergeItem]
    errors: list[Issue]


@dataclass(frozen=True)
class Receipt:
    id: UUID
    session_id: UUID
    import_id: UUID | None
    fingerprint: str
    new_count: int
    changed_count: int
    unchanged_count: int
    conflict_count: int
    error_count: int
    created_at: datetime
