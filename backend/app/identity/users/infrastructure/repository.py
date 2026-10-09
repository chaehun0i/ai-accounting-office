from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.identity.users.domain.entities import User
from app.identity.users.infrastructure.models import UserModel


class UserRepository:
    """Identity Control Plane의 전역 사용자 조회입니다. 회사 업무 조회에 사용하지 않습니다."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def by_email(self, email: str, *, lock: bool = False) -> User | None:
        query = select(UserModel).where(UserModel.email == email)
        row = self.session.scalar(query.with_for_update() if lock else query)
        return self._entity(row)

    def get(self, user_id: UUID, *, lock: bool = False) -> User | None:
        query = select(UserModel).where(UserModel.id == user_id)
        row = self.session.scalar(query.with_for_update() if lock else query)
        return self._entity(row)

    @staticmethod
    def _entity(row: UserModel | None) -> User | None:
        return (
            None
            if row is None
            else User(**{key: getattr(row, key) for key in User.__dataclass_fields__})
        )

    def add(self, user: User) -> None:
        self.session.add(UserModel(**asdict(user)))
        self.session.flush()

    def save(self, user: User) -> None:
        self.session.execute(
            update(UserModel).where(UserModel.id == user.id).values(**asdict(user))
        )
