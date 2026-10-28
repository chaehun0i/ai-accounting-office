"""Independent committed PostgreSQL transactions prove replay and snapshot sealing."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.companies.infrastructure.seed import seed_permissions
from app.core.config import Settings
from app.main import create_app
from app.reporting.cash_flow.snapshot_models import CashFlowLineModel, CashFlowStatementModel
from tests.integration.test_cash_flow_snapshot import ready_snapshot
from tests.integration.test_closing_workflow import request


def test_committed_parallel_generation_and_late_child_insert_seal(db_engine, tmp_path):
    name = "cf_snapshot_" + uuid4().hex + "_test"
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
            _, writer, payload, _, _ = ready_snapshot(
                client, (client.app.state.services.auth, connection)
            )
            # Fixture seeding uses its own connection; make all fixture changes visible.
            connection.commit()
            barrier = Barrier(4)
            keys = ["same-key", "same-key", "another-key", "third-key"]

            def submit(index):
                barrier.wait(timeout=30)
                return request(client, writer, "/cash-flow/generate", payload, keys[index])

            with ThreadPoolExecutor(max_workers=4) as pool:
                responses = list(pool.map(submit, range(4)))
            assert [r.status_code for r in responses] == [201] * 4, [r.text for r in responses]
            assert all(r.json() == responses[0].json() for r in responses)
            snapshot = responses[0].json()
            with Session(engine) as session:
                assert session.scalar(select(func.count()).select_from(CashFlowStatementModel)) == 1
            # This is a new top-level transaction, unlike the savepoint lifecycle tests.
            with pytest.raises(IntegrityError, match="sealed"), Session(engine) as session:
                session.add(
                    CashFlowLineModel(
                        id=uuid4(),
                        company_id=UUID(writer["X-Company-ID"]),
                        statement_id=UUID(snapshot["id"]),
                        line_code="LATE_APPEND",
                        amount=0,
                        source_type="TOTAL",
                        event_id=None,
                        adjustment_id=None,
                        display_order=9999,
                    )
                )
                session.commit()
            assert (
                client.get(f"/cash-flow/{snapshot['id']}/lines", headers=writer).status_code == 200
            )
        # The migration has a real reverse path and can be applied again.
        with engine.connect() as connection:
            config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.downgrade(config, "026_cash_flow_indirect")
            command.upgrade(config, "head")
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
