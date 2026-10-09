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
