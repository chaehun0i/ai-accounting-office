"""Exercise the same real SCE journey with separately committed database connections."""

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.companies.infrastructure.seed import seed_permissions
from app.core.config import Settings
from app.main import create_app
from tests.integration.test_equity_statement import (
    test_equity_rollforward_uses_prior_bs_and_current_is as _journey,
)


def test_independent_connections_approve_once(db_engine, tmp_path):
    name = "equity_review_" + uuid4().hex + "_test"
    with db_engine.execution_options(isolation_level="AUTOCOMMIT").connect() as connection:
        connection.execute(text('CREATE DATABASE "' + name + '"'))
    engine = create_engine(db_engine.url.set(database=name), hide_parameters=True)
    try:
        with engine.connect() as connection:
            config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with Session(engine) as session:
            seed_permissions(session)
            session.commit()
        settings = Settings(
            _env_file=None,
            app_environment="test",
            postgres_url=SecretStr(engine.url.render_as_string(hide_password=False)),
            redis_url=SecretStr("redis://localhost:6379/0"),
            auth_signing_key=SecretStr("test-equity-review-only-signing-key-at-least-32-bytes"),
            storage_root=str(tmp_path),
        )
        with TestClient(create_app(settings), headers={"X-CSRF-Protection": "1"}) as client:
            with engine.connect() as connection:
                _journey(
                    client, (client.app.state.services.auth, connection), False, concurrent=True
                )
    finally:
        engine.dispose()
        with db_engine.execution_options(isolation_level="AUTOCOMMIT").connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
