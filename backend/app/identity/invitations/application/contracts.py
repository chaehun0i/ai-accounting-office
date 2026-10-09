from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.companies.application.contracts import CompanyUnitOfWork


@dataclass
class Invitation:
    id: UUID
    company_id: UUID
    email: str
    role_code: str
    invite_token_hash: str
    invited_by: UUID
    expires_at: datetime
    created_at: datetime
    status: str = "PENDING"
    accepted_by: UUID | None = None
    accepted_at: datetime | None = None


class Invitations(Protocol):
    def pending(self, company_id: UUID, email: str, now: datetime) -> bool: ...
    def add(self, invitation: Invitation) -> None: ...
    def for_token(self, token_hash: str, email: str) -> Invitation | None: ...
    def get(self, company_id: UUID, invitation_id: UUID) -> Invitation | None: ...
    def save(self, invitation: Invitation) -> None: ...


class InvitationUnitOfWork(CompanyUnitOfWork, Protocol):
    @property
    def invitations(self) -> Invitations: ...
