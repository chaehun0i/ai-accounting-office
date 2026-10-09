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
                raise ValueError("연결 주소의 형식이 올바르지 않습니다.") from None
        origin = self.frontend_origin
        if origin.username or origin.password or origin.query or origin.fragment:
            raise ValueError(
                "프론트엔드 주소에는 로그인 정보, 쿼리 또는 프래그먼트를 넣을 수 없습니다."
            )
        if origin.path not in (None, "/"):
            raise ValueError("프론트엔드 주소는 경로 없이 입력해 주세요.")
        if self.app_environment in ("staging", "production") and origin.scheme != "https":
            raise ValueError("스테이징과 운영 환경의 프론트엔드 주소는 HTTPS를 사용해야 합니다.")
        return self


def load_settings() -> Settings:
    try:
        return Settings()
    except ValueError:
        # 시작 실패 진단에 입력된 비밀번호 등 민감정보가 노출되지 않도록 합니다.
        raise RuntimeError(
            "설정을 확인해 주세요. 필수 환경변수와 값의 형식은 docs/environment.md를 참고해 주세요."
        ) from None
