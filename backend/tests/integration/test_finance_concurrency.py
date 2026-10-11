"""별도 사용자·별도 DB 연결의 동시 확정에서 초과 정산을 막습니다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command as migration
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.companies.infrastructure.models import MembershipModel
from app.companies.infrastructure.seed import seed_permissions
from app.core.config import Settings
from app.main import create_app
from tests.integration.test_finance_allocations import confirm, make_record, make_source
from tests.integration.test_finance_flow import allocate, finance_setup


@pytest.mark.parametrize("kind", ["AR", "AP"])
def test_parallel_settlement_independent_actors(db_engine, kind):
    name = "finance_" + uuid4().hex + "_test"
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
            owner, writer, payload, accounts, cp, _ = finance_setup(
                client, (client.app.state.services.auth, connection)
            )
            target = make_source(client, owner, writer, payload, accounts, cp, kind, 100)
            records = []
            for _ in range(2):
                path, record = make_record(client, owner, writer, payload, accounts, cp, kind, 60)
                records.append(allocate(client, writer, path, record, [(target, 60)]))
            response = client.post(
                "/auth/register",
                json={"email": "second-accountant@example.com", "password": "StrongPassword!2026"},
            )
            assert response.status_code == 201, response.text
            second = {**writer, "Authorization": "Bearer " + response.json()["access_token"]}
            user = client.get("/auth/me", headers=second).json()
            with Session(engine) as session:
                session.add(
                    MembershipModel(
                        id=uuid4(),
                        company_id=UUID(writer["X-Company-ID"]),
                        user_id=UUID(user["id"]),
                        role_code="ACCOUNTANT",
                        status="ACTIVE",
                        joined_at=datetime.now(UTC),
                        version=1,
                    )
                )
                session.commit()
            barrier = Barrier(2)
            keys = [str(uuid4()), str(uuid4())]

            def execute(index):
                barrier.wait(timeout=10)
                return confirm(
                    client, writer if index == 0 else second, path, records[index], keys[index]
                )

            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(execute, range(2)))
            assert sorted(result.status_code for result in results) == [200, 409]
            loser = next(result for result in results if result.status_code == 409)
            assert loser.json()["code"] == "SETTLEMENT_TARGET_STALE"
            targets = "receivables" if kind == "AR" else "payables"
            remaining = client.get(
                f"/{targets}/{target['id']}?as_of=2026-01-31", headers=writer
            ).json()
            assert remaining["outstanding_amount"] == "40.0000"
            assert remaining["version"] == 2
            winner = next(i for i, result in enumerate(results) if result.status_code == 200)
            replay = confirm(
                client, writer if winner == 0 else second, path, records[winner], keys[winner]
            )
            assert replay.status_code == 200 and replay.json() == results[winner].json()
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
