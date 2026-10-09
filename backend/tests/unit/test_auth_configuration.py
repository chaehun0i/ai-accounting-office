import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_production_requires_unique_signing_key() -> None:
    values = dict(
        _env_file=None,
        app_environment="production",
        postgres_url=SecretStr("postgresql://local:example@localhost/local"),
        redis_url=SecretStr("redis://localhost:6379/0"),
        frontend_origin="https://accounting.example.com",
    )
    for key in (None, SecretStr("short"), SecretStr("local_placeholder_generate_a_unique_key")):
        with pytest.raises(ValidationError):
            Settings(**values, auth_signing_key=key)
    assert Settings(
        **values, auth_signing_key=SecretStr("test-only-unique-key-with-32-bytes-or-more")
    )
