from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class Approval:
    id: UUID
    company_id: UUID
    journal_id: UUID
    target_version: int
    target_digest: str
    action_code: str
    status: str
    requester_id: UUID
    reviewer_id: UUID | None
    requested_at: datetime
    decided_at: datetime | None
    expires_at: datetime
    reason: str
