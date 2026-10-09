from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.identity.users.domain.entities import User


class RegisterCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)


class LoginCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    status: str
    email_verified_at: datetime | None
    last_login_at: datetime | None

    @classmethod
    def from_user(cls, user: User) -> "UserRead":
        return cls(
            id=user.id,
            email=user.email,
            status=user.status,
            email_verified_at=user.email_verified_at,
            last_login_at=user.last_login_at,
        )


class AuthRead(BaseModel):
    user: UserRead
    access_token: str = Field(repr=False)
    token_type: str = "bearer"
    expires_in: int


class CommandResult(BaseModel):
    success: bool = True
