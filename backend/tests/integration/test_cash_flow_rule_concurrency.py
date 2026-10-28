"""Identical first rule writes replay across independent PostgreSQL connections."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
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
from tests.integration.test_journal_flow import prepare


def test_parallel_identical_rules_replay(db_engine, tmp_path):
    name = "cf_rules_" + uuid4().hex + "_test"
    admin = db_engine.execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
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
            auth_signing_key=SecretStr("test-only-signing-key-with-at-least-32-bytes"),
            storage_root=str(tmp_path),
        )
        with (
            TestClient(create_app(settings), headers={"X-CSRF-Protection": "1"}) as client,
            engine.connect() as connection,
        ):
            _, writer, _, _ = prepare(client, (client.app.state.services.auth, connection))
            account = next(
                row
                for row in client.get("/accounts", headers=writer).json()
                if row["account_code"] == "4010"
            )
            payload = {
                "account_id": account["id"],
                "adjustment_code": "OPERATING_RESULT",
                "source_mapping_type": "ACCOUNT_LEDGER",
                "effective_from": "2026-01-01",
                "policy_code": "TAX_INTEREST_OPERATING",
                "policy_version": 1,
            }
            barrier = Barrier(2)

            def submit(_index):
                barrier.wait(timeout=30)
                return client.post("/cash-flow/adjustment-rules", headers=writer, json=payload)

            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(submit, range(2)))
            assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
            assert responses[0].json() == responses[1].json()
            assert len(client.get("/cash-flow/adjustment-rules", headers=writer).json()) == 1
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
