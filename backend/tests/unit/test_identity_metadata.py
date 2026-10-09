from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable

from app.identity.sessions.infrastructure.models import RefreshSessionModel
from app.identity.users.infrastructure.models import UserModel


def test_identity_storage_is_explicit_and_hash_only() -> None:
    assert "refresh_token" not in RefreshSessionModel.__table__.columns
    assert "jti" not in RefreshSessionModel.__table__.columns
    assert "password" not in UserModel.__table__.columns
    assert "UUID" in str(CreateTable(UserModel.__table__).compile(dialect=dialect()))
    assert RefreshSessionModel.__table__.c.refresh_token_hash.unique
