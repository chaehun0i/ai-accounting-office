"""독립 PostgreSQL 연결에서 원천·대상 초과대사를 검증합니다."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command as migration
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.companies.infrastructure.seed import seed_permissions
from app.core.config import Settings
from app.main import create_app
from tests.integration.test_bank_reconciliation import command, prepare_bank, target


@pytest.mark.parametrize(
    "mode", ["same_source", "same_target", "same_confirm", "same_key", "unmatch_confirm"]
)
def test_parallel_reconciliation_independent_connections(db_engine, mode, tmp_path):
    name = "bank_race_" + uuid4().hex + "_test"
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
            storage_root=str(tmp_path),
        )
        with (
            TestClient(create_app(settings), headers={"X-CSRF-Protection": "1"}) as client,
            engine.connect() as connection,
        ):
            content = b"source_id,date,amount,currency,direction\nb1,2026-01-02,100,KRW,IN\n"
            if mode == "same_target":
                content += b"b2,2026-01-02,100,KRW,IN\n"
            _, writer, payload = prepare_bank(
                client,
                (client.app.state.services.auth, connection),
                content,
                closing_balance="200" if mode == "same_target" else "100",
            )
            first_target = target(client, writer, source_id="t1")
            second_target = (
                target(client, writer, source_id="t2") if mode == "same_source" else first_target
            )
            result = command(client, writer, "/bank-statements/imports", payload)
            assert result.status_code == 200, result.text
            statement = result.json()
            sources = client.get(
                f"/bank-statements/{statement['id']}/transactions", headers=writer
            ).json()
            candidates = client.post(
                f"/bank-statements/{statement['id']}/match-candidates", headers=writer
            ).json()
            drafts = []
            for index, transaction in enumerate([first_target, second_target]):
                source = sources[index] if mode == "same_target" else sources[0]
                candidate = next(
                    value
                    for value in candidates
                    if value["source_id"] == source["id"]
                    and value["target_id"] == transaction["id"]
                )
                draft = command(
                    client,
                    writer,
                    "/reconciliations",
                    {
                        "lines": [
                            {
                                "source_type": "BANK",
                                "source_id": source["id"],
                                "target_type": "TRANSACTION",
                                "target_id": transaction["id"],
                                "amount": "100",
                                "source_version": candidate["source_version"],
                                "target_version": candidate["target_version"],
                            }
                        ]
                    },
                )
                assert draft.status_code == 201, draft.text
                drafts.append(draft.json())
            if mode in {"same_confirm", "same_key"}:
                drafts[1] = drafts[0]
            if mode == "unmatch_confirm":
                saved = command(
                    client,
                    writer,
                    f"/reconciliations/{drafts[0]['id']}/confirm",
                    {"expected_version": drafts[0]["version"]},
                )
                assert saved.status_code == 200, saved.text
                drafts = [saved.json(), saved.json()]
            keys = [str(uuid4()), str(uuid4())]
            if mode == "same_key":
                keys[1] = keys[0]
            barrier = Barrier(2)

            def execute(index):
                barrier.wait(timeout=30)
                value = drafts[index]
                action = "unmatch" if mode == "unmatch_confirm" and index == 0 else "confirm"
                body = {"expected_version": value["version"]}
                if action == "unmatch":
                    body["reason"] = "동시 해제 검토"
                return command(
                    client,
                    writer,
                    f"/reconciliations/{value['id']}/{action}",
                    body,
                    keys[index],
                )

            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(execute, range(2)))
            assert sorted(value.status_code for value in results) == (
                [200, 200] if mode == "same_key" else [200, 409]
            ), [(value.status_code, value.text) for value in results]
            sources = client.get(
                f"/bank-statements/{statement['id']}/transactions", headers=writer
            ).json()
            from decimal import Decimal

            assert sum(
                (Decimal(value["matched_amount"]) for value in sources), Decimal(0)
            ) == Decimal(0 if mode == "unmatch_confirm" else 100)
            assert all(
                Decimal(value["matched_amount"]) <= Decimal(value["amount"]) for value in sources
            )
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
