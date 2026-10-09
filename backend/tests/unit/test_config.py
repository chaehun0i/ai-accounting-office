import pytest
from pydantic import ValidationError

from app.core.config import Settings, load_settings


def test_environment_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv(
        "POSTGRES_URL", "postgresql://local:private-password@localhost:5432/accounting"
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("BACKEND_PORT", "8100")
    settings = Settings(_env_file=None)
    assert settings.backend_port == 8100
    assert settings.app_environment == "test"
    assert "private-password" not in repr(settings)


def test_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("APP_ENVIRONMENT", "POSTGRES_URL", "REDIS_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "key,value",
    [
        ("APP_ENVIRONMENT", "unknown"),
        ("BACKEND_PORT", "0"),
        ("BACKEND_PORT", "65536"),
        ("POSTGRES_URL", "https://private-password.example"),
        ("REDIS_URL", "not-a-url"),
        ("FRONTEND_ORIGIN", "http://localhost:3000/path"),
    ],
)
def test_invalid_configuration(monkeypatch: pytest.MonkeyPatch, key: str, value: str) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://local:placeholder@localhost:5432/accounting")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    with pytest.raises(RuntimeError, match="Invalid configuration") as caught:
        load_settings()
    assert "private-password" not in str(caught.value)


def test_production_requires_https(settings: Settings) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**settings.model_dump(), "app_environment": "production"})
