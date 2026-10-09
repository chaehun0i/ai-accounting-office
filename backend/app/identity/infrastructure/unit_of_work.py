from datetime import datetime
from typing import Self

from sqlalchemy import func, select

from app.core.database.unit_of_work import SQLAlchemyUnitOfWork
from app.identity.sessions.infrastructure.repository import (
    SecurityEventRepository,
    SessionRepository,
)
from app.identity.users.infrastructure.repository import UserRepository


class IdentitySQLAlchemyUnitOfWork(SQLAlchemyUnitOfWork):
    users: UserRepository
    sessions: SessionRepository
    security: SecurityEventRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.users = UserRepository(self.session)
        self.sessions = SessionRepository(self.session)
        self.security = SecurityEventRepository(self.session)
        return self

    def now(self) -> datetime:
        value: datetime = self.session.execute(select(func.clock_timestamp())).scalar_one()
        return value
