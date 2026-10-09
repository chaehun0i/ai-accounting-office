from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.contracts.access_errors import AuthenticationRequired, InvalidInput
from app.core.security import PasswordSecurity, TokenClaims, TokenSecurity, random_token
from app.identity.users.domain.entities import normalize_email


def test_password_and_email_policy() -> None:
    security = PasswordSecurity()
    encoded = security.hash("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert security.verify("correct horse battery staple", encoded)
    assert not security.verify("wrong", encoded)
    assert not security.verify("wrong", None)
    with pytest.raises(InvalidInput):
        security.hash("short")
    assert normalize_email("  Person@Example.COM ") == "person@example.com"


def test_tokens_reject_expiry_wrong_type_and_malformed() -> None:
    security = TokenSecurity("test-only-signing-key-with-at-least-32-bytes")
    claims = TokenClaims(uuid4(), uuid4(), random_token())
    now = datetime.now(UTC)
    access = security.issue("access", claims, now)
    assert security.read(access, "access") == claims
    for value in [
        "broken",
        access + "x",
        security.issue("access", claims, now - timedelta(days=1)),
    ]:
        with pytest.raises(AuthenticationRequired):
            security.read(value, "access")
    with pytest.raises(AuthenticationRequired):
        security.read(access, "refresh")
