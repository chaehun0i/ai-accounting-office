from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, select
from sqlalchemy.orm import sessionmaker

from app.contracts.access_errors import AuthenticationRequired
from app.core.security import PasswordSecurity, TokenSecurity, digest
from app.identity.auth.application.service import AuthService
from app.identity.infrastructure.unit_of_work import IdentitySQLAlchemyUnitOfWork
from app.identity.sessions.domain.entities import RequestFacts
from app.identity.sessions.infrastructure.models import (
    IdentitySecurityEventModel,
    RefreshSessionModel,
)


@pytest.fixture(scope="session")
def identity_database(db_engine: Engine) -> Engine:
    with db_engine.connect() as connection:
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return db_engine


@pytest.fixture
def auth_service(identity_database: Engine) -> Iterator[tuple[AuthService, Connection]]:
    with identity_database.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            autobegin=False,
            join_transaction_mode="create_savepoint",
        )
        service = AuthService(
            lambda: IdentitySQLAlchemyUnitOfWork(factory),
            PasswordSecurity(),
            TokenSecurity("test-only-signing-key-with-at-least-32-bytes"),
        )
        try:
            yield service, connection
        finally:
            transaction.rollback()


def facts() -> RequestFacts:
    return RequestFacts(uuid4(), "192.0.2.0/24")


def test_register_login_and_rotation(auth_service: tuple[AuthService, Connection]) -> None:
    service, connection = auth_service
    result = service.register(" Person@Example.com ", "correct horse battery staple", facts())
    assert result.user.email == "person@example.com"
    assert result.user.password_hash != "correct horse battery staple"
    assert service.authenticate(result.access_token).user_id == result.user.id
    with pytest.raises(AuthenticationRequired):
        service.register("person@example.com", "correct horse battery staple", facts())
    with pytest.raises(AuthenticationRequired):
        service.login("person@example.com", "wrong", facts())
    logged_in = service.login("person@example.com", "correct horse battery staple", facts())
    rotated = service.refresh(logged_in.refresh_token, facts())
    sessions = connection.execute(select(RefreshSessionModel.__table__)).mappings().all()
    assert all(
        row["refresh_token_hash"] not in {logged_in.refresh_token, rotated.refresh_token}
        for row in sessions
    )
    assert len({row["session_family_id"] for row in sessions}) == 2
    assert any(row["status"] == "ROTATED" for row in sessions)
    with pytest.raises(AuthenticationRequired):
        service.refresh(logged_in.refresh_token, facts())
    with pytest.raises(AuthenticationRequired):
        service.refresh(rotated.refresh_token, facts())
    with pytest.raises(AuthenticationRequired):
        service.authenticate(rotated.access_token)
    codes = connection.scalars(select(IdentitySecurityEventModel.event_code)).all()
    assert "REFRESH_REUSED" in codes
    assert "SESSION_FAMILY_REVOKED" in codes
    assert service.authenticate(result.access_token)


def test_logout_and_all_sessions(auth_service: tuple[AuthService, Connection]) -> None:
    service, _ = auth_service
    first = service.register("user@example.com", "correct horse battery staple", facts())
    second = service.login("user@example.com", "correct horse battery staple", facts())
    service.logout(service.authenticate(first.access_token), facts())
    with pytest.raises(AuthenticationRequired):
        service.authenticate(first.access_token)
    service.logout(service.authenticate(second.access_token), facts(), all_sessions=True)
    with pytest.raises(AuthenticationRequired):
        service.refresh(second.refresh_token, facts())


def test_expiry_and_hash_mismatch(auth_service: tuple[AuthService, Connection]) -> None:
    service, _ = auth_service
    result = service.register("user@example.com", "correct horse battery staple", facts())
    claims = service.tokens.read(result.refresh_token, "refresh")
    with service.factory() as uow:
        session = uow.sessions.get(claims.user_id, claims.session_id)
        assert session is not None
        session.refresh_token_hash = digest("wrong")
        uow.sessions.save(session)
    with pytest.raises(AuthenticationRequired):
        service.refresh(result.refresh_token, facts())
    with service.factory() as uow:
        session = uow.sessions.get(claims.user_id, claims.session_id)
        assert session is not None
        session.refresh_token_hash = digest(result.refresh_token)
        session.issued_at = uow.now() - timedelta(days=2)
        session.expires_at = uow.now() - timedelta(days=1)
        uow.sessions.save(session)
    with pytest.raises(AuthenticationRequired):
        service.refresh(result.refresh_token, facts())
