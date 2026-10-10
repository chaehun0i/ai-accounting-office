"""독립 DB 연결에서 동시 확정 번호와 중복 확정 차단을 검증합니다."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from alembic import command as migration
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.companies.infrastructure.seed import seed_permissions
from app.core.config import Settings
from app.main import create_app
from tests.integration.test_journal_flow import command, prepare
from tests.integration.test_journal_security import approved, create


def test_parallel_posting_independent_connections(db_engine):
    name = "posting_" + uuid4().hex + "_test"
    admin = db_engine.execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + name + '"'))
    url = db_engine.url.set(database=name)
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
            config.attributes["connection"] = connection
            migration.upgrade(config, "head")
        with Session(engine) as session:
            seed_permissions(session)
            session.commit()
        settings = Settings(
            _env_file=None,
            app_environment="test",
            postgres_url=SecretStr(url.render_as_string(hide_password=False)),
            redis_url=SecretStr("redis://localhost:6379/0"),
            auth_signing_key=SecretStr("test-only-signing-key-with-at-least-32-bytes"),
        )
        with (
            TestClient(create_app(settings), headers={"X-CSRF-Protection": "1"}) as client,
            engine.connect() as connection,
        ):
            owner, writer, payload, _ = prepare(
                client, (client.app.state.services.auth, connection)
            )
            journals = [
                approved(client, owner, writer, create(client, writer, payload)) for _ in range(2)
            ]
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda j: command(client, owner, j, "post"), journals))
            assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
            assert {r.json()["journal_no"] for r in results} == {"J-2026-000001", "J-2026-000002"}
            duplicate = approved(client, owner, writer, create(client, writer, payload))
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(
                    workers.map(lambda _: command(client, owner, duplicate, "post"), range(2))
                )
            assert sorted(r.status_code for r in results) == [200, 409]
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
