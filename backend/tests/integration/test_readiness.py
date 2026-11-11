from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database.readiness import DatabaseReadiness, migration_heads
from app.health import router


def test_actual_postgres_and_revision_readiness_is_read_only(identity_database):
    engine = identity_database
    with engine.connect() as connection:
        before = tuple(connection.scalars(text("SELECT version_num FROM alembic_version")))
    app = FastAPI()
    app.include_router(router)
    app.state.database_readiness = DatabaseReadiness(engine, migration_heads())
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 200, response.text
        assert response.json()["postgres"] == "available"
        assert response.json()["migrations"] == "current"
        assert response.json()["llm"] == "not_probed"
        app.state.database_readiness = DatabaseReadiness(engine, ("unapplied-revision",))
        mismatch = client.get("/ready")
        assert mismatch.status_code == 503
        assert mismatch.json()["reason_code"] == "MIGRATION_MISMATCH"
        assert client.get("/health").status_code == 200
    with engine.connect() as connection:
        assert tuple(connection.scalars(text("SELECT version_num FROM alembic_version"))) == before
