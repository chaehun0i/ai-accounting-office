"""검증된 KDF/JWT 라이브러리와 비밀값을 출력하지 않는 보안 primitive입니다."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.contracts.access_errors import AuthenticationRequired, InvalidInput


class PasswordSecurity:
    def __init__(self) -> None:
        self.hasher = PasswordHasher()
        self._dummy = self.hasher.hash(secrets.token_urlsafe(32))

    def hash(self, value: str) -> str:
        if not 12 <= len(value) <= 128 or len(value.encode()) > 512:
            raise InvalidInput()
        return self.hasher.hash(value)

    def verify(self, value: str, encoded: str | None) -> bool:
        if len(value) > 128:
            return False
        try:
            valid = self.hasher.verify(encoded or self._dummy, value)
            return valid and encoded is not None
        except (VerificationError, InvalidHashError):
            return False


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def random_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    session_id: UUID
    jti: str


class TokenSecurity:
    def __init__(self, key: str, access_seconds: int = 600, refresh_seconds: int = 2592000) -> None:
        if len(key.encode()) < 32:
            raise ValueError("인증 서명 키는 32바이트 이상으로 설정해 주세요.")
        self._key = key
        self.access_seconds = access_seconds
        self.refresh_seconds = refresh_seconds

    def issue(self, kind: str, claims: TokenClaims, now: datetime) -> str:
        ttl = self.access_seconds if kind == "access" else self.refresh_seconds
        return jwt.encode(
            {
                "sub": str(claims.user_id),
                "sid": str(claims.session_id),
                "jti": claims.jti,
                "iat": now,
                "exp": now + timedelta(seconds=ttl),
                "typ": kind,
                "iss": "ai-accounting-office",
                "aud": f"aao-{kind}",
            },
            self._key,
            algorithm="HS256",
        )

    def read(self, value: str, kind: str) -> TokenClaims:
        try:
            if len(value) > 4096:
                raise ValueError
            data = jwt.decode(
                value,
                self._key,
                algorithms=["HS256"],
                issuer="ai-accounting-office",
                audience=f"aao-{kind}",
                options={"require": ["sub", "sid", "jti", "iat", "exp", "typ"]},
            )
            if data["typ"] != kind or not isinstance(data["jti"], str) or len(data["jti"]) != 43:
                raise ValueError
            if (
                type(data["iat"]) is not int
                or type(data["exp"]) is not int
                or data["exp"] <= data["iat"]
            ):
                raise ValueError
            return TokenClaims(UUID(data["sub"]), UUID(data["sid"]), data["jti"])
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError):
            raise AuthenticationRequired() from None
