from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class RefreshSession:
    id: UUID
    user_id: UUID
    session_family_id: UUID
    refresh_token_hash: str = field(repr=False)
    jti_hash: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime
    status: str = "ACTIVE"
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    user_agent_hash: str | None = None
    ip_prefix: str | None = None
    last_seen_at: datetime | None = None


@dataclass(frozen=True)
class RequestFacts:
    request_id: UUID
    ip_prefix: str
    user_agent_hash: str | None = None
