"""세션은 UoW가 열고 닫으며, 암묵적 새 트랜잭션은 허용하지 않습니다."""

from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(bind: Engine | Connection) -> sessionmaker[Session]:
    return sessionmaker(bind=bind, autoflush=False, expire_on_commit=False, autobegin=False)
