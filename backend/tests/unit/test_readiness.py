from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.database.readiness import DatabaseReadiness, migration_heads
from app.main import create_app


def test_liveness_remains_available_and_database_errors_are_redacted(settings):
    engine = MagicMock()
    engine.begin.side_effect = OperationalError("SELECT secret", {}, Exception("private-password"))
    app = create_app(settings)
    app.state.database_readiness = DatabaseReadiness(engine, ("head",))
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["reason_code"] == "DATABASE_UNAVAILABLE"
        assert "private-password" not in response.text
        assert "SELECT" not in response.text
        assert response.headers["cache-control"] == "no-store"


def test_missing_metadata_is_not_reported_as_current():
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.scalar.return_value = 1
    connection.scalars.side_effect = ProgrammingError("secret table", {}, Exception("private-host"))
    result = DatabaseReadiness(engine, ("head",)).inspect()
    assert result.status == "not_ready"
    assert result.postgres == "available"
    assert result.reason_code == "MIGRATION_UNAVAILABLE"
    assert "private-host" not in result.model_dump_json()


def test_empty_or_wrong_migration_revision_never_becomes_ready():
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.scalar.return_value = 1
    for actual in ([], ["old-head"], ["head", "unexpected-branch"]):
        connection.scalars.return_value = actual
        assert DatabaseReadiness(engine, ("head",)).inspect().reason_code == "MIGRATION_MISMATCH"
    assert len(migration_heads()) == 1
