from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.contracts.unit_of_work import UnitOfWork
from app.identity.sessions.domain.entities import RefreshSession, RequestFacts
from app.identity.users.domain.entities import User


class Users(Protocol):
    def by_email(self, email: str, *, lock: bool = False) -> User | None: ...
    def get(self, user_id: UUID, *, lock: bool = False) -> User | None: ...
    def add(self, user: User) -> None: ...
    def save(self, user: User) -> None: ...


class Sessions(Protocol):
    def get(self, user_id: UUID, session_id: UUID) -> RefreshSession | None: ...
    def add(self, session: RefreshSession) -> None: ...
    def save(self, session: RefreshSession) -> None: ...
    def revoke(
        self,
        user_id: UUID,
        now: datetime,
        reason: str,
        *,
        family_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> None: ...


class SecurityEvents(Protocol):
    def record(
        self,
        code: str,
        facts: RequestFacts,
        *,
        user_id: UUID | None = None,
        session: RefreshSession | None = None,
        email_hash: str | None = None,
    ) -> None: ...
    def limit(
        self, action: str, facts: RequestFacts, now: datetime, email_hash: str | None = None
    ) -> None: ...


class IdentityUnitOfWork(UnitOfWork, Protocol):
    users: Users
    sessions: Sessions
    security: SecurityEvents

    def now(self) -> datetime: ...
