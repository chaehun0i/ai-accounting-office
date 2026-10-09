from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import Engine, delete, select

from app.contracts.access_errors import AuthenticationRequired
from app.core.database.session import create_session_factory
from app.core.security import PasswordSecurity, TokenSecurity
from app.identity.auth.application.service import AuthService
from app.identity.infrastructure.unit_of_work import IdentitySQLAlchemyUnitOfWork
from app.identity.sessions.domain.entities import RequestFacts
from app.identity.sessions.infrastructure.models import (
    IdentitySecurityEventModel,
    RefreshSessionModel,
)
from app.identity.users.infrastructure.models import UserModel


def test_concurrent_refresh_preserves_family_history(identity_database: Engine) -> None:
    factory = create_session_factory(identity_database)
    service = AuthService(
        lambda: IdentitySQLAlchemyUnitOfWork(factory),
        PasswordSecurity(),
        TokenSecurity("concurrency-test-signing-key-at-least-32-bytes"),
    )
    result = service.register(
        f"{uuid4()}@example.com",
        "correct horse battery staple",
        RequestFacts(uuid4(), "198.51.100.0/24"),
    )
    barrier = Barrier(2)

    def refresh(index: int) -> str:
        barrier.wait(timeout=10)
        try:
            service.refresh(result.refresh_token, RequestFacts(uuid4(), f"192.0.{index}.0/24"))
            return "rotated"
        except AuthenticationRequired:
            return "reused"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(refresh, (1, 2)))
        assert sorted(outcomes) == ["reused", "rotated"]
        with identity_database.connect() as connection:
            rows = (
                connection.execute(
                    select(RefreshSessionModel.__table__).where(
                        RefreshSessionModel.user_id == result.user.id
                    )
                )
                .mappings()
                .all()
            )
            assert len(rows) == 2
            assert len({row["session_family_id"] for row in rows}) == 1
            assert {row["status"] for row in rows} == {"REVOKED"}
            events = connection.scalars(
                select(IdentitySecurityEventModel.event_code).where(
                    IdentitySecurityEventModel.user_id == result.user.id
                )
            ).all()
            assert "REFRESH_REUSED" in events
    finally:
        # 이 검사에서 생성한 전용 계정의 테스트 데이터만 정리합니다.
        with identity_database.begin() as connection:
            for model in (IdentitySecurityEventModel, RefreshSessionModel):
                connection.execute(delete(model).where(model.user_id == result.user.id))
            connection.execute(delete(UserModel).where(UserModel.id == result.user.id))
