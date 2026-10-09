import pytest
from pydantic import SecretStr

from app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_environment="test",
        postgres_url=SecretStr("postgresql://local:placeholder@localhost:5432/accounting"),
        redis_url=SecretStr("redis://localhost:6379/0"),
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--require-postgres",
        action="store_true",
        help="PostgreSQL 통합 테스트를 생략하지 않고 연결 설정을 필수로 요구합니다.",
    )
