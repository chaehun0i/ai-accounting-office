from ipaddress import IPv4Address, IPv6Address
from typing import Literal, Self

from pydantic import Field, HttpUrl, PostgresDsn, RedisDsn, SecretStr, TypeAdapter, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore", hide_input_in_errors=True)

    app_environment: Literal["local", "test", "staging", "production"]
    postgres_url: SecretStr
    redis_url: SecretStr
    backend_host: IPv4Address | IPv6Address = IPv4Address("127.0.0.1")
    backend_port: int = Field(default=8000, ge=1, le=65535)
    frontend_origin: HttpUrl = HttpUrl("http://localhost:3000")

    @model_validator(mode="after")
    def validate_connection_urls(self) -> Self:
        for value, kind in [(self.postgres_url, PostgresDsn), (self.redis_url, RedisDsn)]:
            try:
                TypeAdapter(kind).validate_python(value.get_secret_value())
            except ValueError:
                raise ValueError("Invalid dependency URL") from None
        origin = self.frontend_origin
        if origin.username or origin.password or origin.query or origin.fragment:
            raise ValueError("Frontend origin must not contain credentials, query or fragment")
        if origin.path not in (None, "/"):
            raise ValueError("Frontend origin must not contain a path")
        if self.app_environment in ("staging", "production") and origin.scheme != "https":
            raise ValueError("Deployed frontend origin must use HTTPS")
        return self


def load_settings() -> Settings:
    try:
        return Settings()
    except ValueError:
        # Do not let Pydantic/uvicorn startup diagnostics reveal input credentials.
        raise RuntimeError("Invalid configuration; check the environment contract") from None
