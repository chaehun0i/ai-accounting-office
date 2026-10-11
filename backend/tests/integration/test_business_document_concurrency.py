"""실제 독립 연결에서 문서 확정·중복 생성·정정 경쟁을 검증합니다."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.companies.infrastructure.seed import seed_permissions
from app.core.config import Settings
from app.main import create_app
from tests.integration.test_business_documents import body, create, note_payload, transition
from tests.integration.test_finance_flow import finance_setup


@pytest.fixture
def isolated_document_client(db_engine):
    name = "documents_" + uuid4().hex + "_test"
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
            auth_signing_key=SecretStr("test-document-only-signing-key-at-least-32-bytes"),
        )
        with (
            TestClient(create_app(settings), headers={"X-CSRF-Protection": "1"}) as client,
            engine.connect() as connection,
        ):
            yield client, finance_setup(client, (client.app.state.services.auth, connection))
    finally:
        engine.dispose()
        with db_engine.execution_options(isolation_level="AUTOCOMMIT").connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))


def parallel(operation):
    barrier = Barrier(2)

    def run(index):
        barrier.wait(timeout=30)
        return operation(index)

    with ThreadPoolExecutor(max_workers=2) as workers:
        return list(workers.map(run, range(2)))


@pytest.mark.parametrize("same_key", [True, False])
def test_parallel_invoice_confirm_single_transaction(isolated_document_client, same_key):
    client, (owner, writer, _, _, cp, _) = isolated_document_client
    draft = create(client, writer, "/sales-invoices", body(cp))
    submitted = transition(client, writer, "/sales-invoices", draft, "submit").json()
    keys = [str(uuid4()), str(uuid4())]
    results = parallel(
        lambda index: transition(
            client,
            owner,
            "/sales-invoices",
            submitted,
            "approve",
            keys[0] if same_key else keys[index],
        )
    )
    assert sorted(response.status_code for response in results) == (
        [200, 200] if same_key else [200, 409]
    )
    if same_key:
        assert results[0].json() == results[1].json()
    transactions = client.get(
        "/transactions?date_from=2026-01-01&date_to=2026-12-31", headers=writer
    ).json()
    assert len(transactions) == 1
    assert len(client.get("/receivables?as_of=2026-12-31", headers=writer).json()) == 1


@pytest.mark.parametrize("same_source", [True, False])
def test_parallel_source_or_document_number_duplicate(isolated_document_client, same_source):
    client, (_, writer, _, _, cp, _) = isolated_document_client

    def execute(index):
        payload = body(cp)
        if not same_source:
            payload["source_id"] = "source-" + str(index)
        return client.post(
            "/sales-invoices", headers={**writer, "Idempotency-Key": str(uuid4())}, json=payload
        )

    results = parallel(execute)
    assert all(response.status_code in {201, 409} for response in results), [
        r.text for r in results
    ]
    assert any(response.status_code == 201 for response in results)
    assert len(client.get("/sales-invoices", headers=writer).json()) == 1


def test_parallel_credit_notes_cannot_exceed_outstanding(isolated_document_client):
    client, (owner, writer, _, _, cp, _) = isolated_document_client
    original = create(client, writer, "/sales-invoices", body(cp))
    original = transition(client, writer, "/sales-invoices", original, "submit").json()
    original = transition(client, owner, "/sales-invoices", original, "approve").json()
    notes = []
    for index in range(2):
        note = create(
            client,
            writer,
            "/credit-notes",
            note_payload(cp, original, "CN-" + str(index), "6000000", "600000"),
        )
        notes.append(transition(client, writer, "/credit-notes", note, "submit").json())
    results = parallel(
        lambda index: transition(client, owner, "/credit-notes", notes[index], "approve")
    )
    assert sorted(response.status_code for response in results) == [200, 422]
    remaining = client.get("/receivables?as_of=2026-12-31", headers=writer).json()
    assert remaining[0]["outstanding_amount"] == "4400000.0000"
    assert (
        len(
            client.get(
                "/transactions?date_from=2026-01-01&date_to=2026-12-31", headers=writer
            ).json()
        )
        == 2
    )
