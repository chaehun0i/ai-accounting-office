from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


def normalize_email(value: str) -> str:
    """인증 식별자는 앞뒤 공백 제거 후 전체 주소를 소문자로 정규화합니다."""
    return value.strip().lower()


@dataclass
class User:
    id: UUID
    email: str
    password_hash: str = field(repr=False)
    status: str = "ACTIVE"
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    session_id: UUID
    email: str
