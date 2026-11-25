"""Focused set assertions reuse the real CLOSED five-statement journey."""

from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.reporting.statement_sets.models import StatementSetRevisionModel
from app.reporting.statement_sets.review_models import StatementSetReviewModel
from tests.integration.test_closing_workflow import request


def exercise(client, owner, writer, reviewer, period, equity, note, connection, concurrent):
    base = "/financial-statement-sets"
    ready = client.get(base + "/readiness", headers=writer, params={"period_id": period["id"]})
    assert ready.status_code == 200 and "EQUITY_APPROVAL_REQUIRED" in ready.json()["issues"], (
        ready.text
    )
    path = f"/equity/statements/{equity['id']}/review"
    assert (
        request(
            client,
            writer,
            path + "/request-review",
            {"expected_version": 0, "reason": "set source"},
        ).status_code
        == 200
    )
    assert (
        request(
            client, reviewer, path + "/approve", {"expected_version": 1, "reason": "checked"}
        ).status_code
        == 200
    )
    ready = client.get(base + "/readiness", headers=writer, params={"period_id": period["id"]})
    assert ready.status_code == 200 and ready.json()["status"] == "READY", ready.text
    key = str(uuid4())
    if concurrent:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            generated = list(
                pool.map(
                    lambda _: request(
                        client, writer, base + "/generate", {"period_id": period["id"]}, key
                    ),
                    range(2),
                )
            )
        assert all(row.status_code == 201 for row in generated), [row.text for row in generated]
        assert generated[0].json()["id"] == generated[1].json()["id"]
        created = generated[0]
    else:
        created = request(client, writer, base + "/generate", {"period_id": period["id"]}, key)
    assert created.status_code == 201, created.text
    bundle = created.json()
    assert bundle["notes_id"] == note["id"] and bundle["equity_id"] == equity["id"]
    assert bundle["snapshot_digest"] == ready.json()["source_digest"]
    replay = request(client, writer, base + "/generate", {"period_id": period["id"]}, key)
    assert replay.status_code == 201 and replay.json()["id"] == bundle["id"]
    valid_other_period = next(
        row["id"]
        for row in client.get("/closing/periods", headers=writer).json()
        if row["id"] != period["id"]
    )
    other = request(client, writer, base + "/generate", {"period_id": valid_other_period}, key)
    assert other.status_code == 409
    assert (
        client.get(
            base + "/" + bundle["id"], headers={**writer, "X-Company-ID": str(uuid4())}
        ).status_code
        == 404
    )
    report = {
        "report_code": "FINANCIAL_STATEMENT_SET",
        "period_id": period["id"],
        "period_preset": "CUSTOM",
        "date_from": period["start_date"],
        "date_to": period["end_date"],
        "format": "CSV",
    }
    blocked_export = request(client, writer, "/reports/generations", report)
    assert blocked_export.status_code == 409, blocked_export.text
    review_path = base + "/" + bundle["id"] + "/review"
    review_key = str(uuid4())
    review_payload = {"expected_version": 0, "reason": "review all five"}
    requested = request(client, writer, review_path + "/request-review", review_payload, review_key)
    assert requested.status_code == 200, requested.text
    replayed = request(client, writer, review_path + "/request-review", review_payload, review_key)
    assert replayed.status_code == 200 and replayed.json()["id"] == requested.json()["id"]
    assert (
        request(
            client,
            writer,
            review_path + "/request-review",
            {**review_payload, "reason": "different"},
            review_key,
        ).status_code
        == 409
    )
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        pending = session.get(StatementSetReviewModel, UUID(requested.json()["id"]))
        assert pending is not None
        direct = {
            column.name: getattr(pending, column.name)
            for column in StatementSetReviewModel.__table__.columns
        }
        with pytest.raises(IntegrityError):
            session.add(
                StatementSetReviewModel(
                    **{
                        **direct,
                        "id": uuid4(),
                        "version": 2,
                        "status": "APPROVED",
                        "idempotency_key": str(uuid4()),
                    }
                )
            )
            session.flush()
        session.rollback()
    assert (
        request(
            client, writer, review_path + "/approve", {"expected_version": 1, "reason": "self"}
        ).status_code
        == 403
    )
    assert (
        request(
            client, reviewer, review_path + "/reject", {"expected_version": 1, "reason": "clarify"}
        ).status_code
        == 200
    )
    assert (
        request(
            client,
            writer,
            review_path + "/request-review",
            {"expected_version": 2, "reason": "ready again"},
        ).status_code
        == 200
    )
    if concurrent:
        with ThreadPoolExecutor(max_workers=2) as pool:
            approvals = list(
                pool.map(
                    lambda headers: request(
                        client,
                        headers,
                        review_path + "/approve",
                        {"expected_version": 3, "reason": "independent"},
                    ),
                    [owner, reviewer],
                )
            )
        assert sorted(row.status_code for row in approvals) == [200, 409], [
            row.text for row in approvals
        ]
        approved = next(row for row in approvals if row.status_code == 200)
    else:
        approved = request(
            client,
            reviewer,
            review_path + "/approve",
            {"expected_version": 3, "reason": "independent"},
        )
    assert approved.status_code == 200, approved.text
    assert (
        request(
            client, reviewer, review_path + "/approve", {"expected_version": 3, "reason": "repeat"}
        ).status_code
        == 409
    )
    for model, identifier, changes in [
        (StatementSetRevisionModel, bundle["id"], {"snapshot_digest": "0" * 64}),
        (StatementSetReviewModel, approved.json()["id"], {"reason": "overwrite"}),
    ]:
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            with pytest.raises(IntegrityError):
                session.execute(update(model).where(model.id == UUID(identifier)).values(**changes))
            session.rollback()
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        original = session.get(StatementSetRevisionModel, UUID(bundle["id"]))
        assert original is not None
        payload = {
            column.name: getattr(original, column.name)
            for column in StatementSetRevisionModel.__table__.columns
        }
        with pytest.raises(IntegrityError):
            session.add(
                StatementSetRevisionModel(
                    **{
                        **payload,
                        "id": uuid4(),
                        "balance_id": original.income_id,
                        "income_id": original.balance_id,
                        "snapshot_digest": "1" * 64,
                    }
                )
            )
            session.flush()
        session.rollback()
    from app.reporting.financial_statements.infrastructure.models import StatementSetModel

    with Session(connection, join_transaction_mode="create_savepoint") as session:
        original_set = session.get(StatementSetModel, UUID(bundle["statement_set_id"]))
        assert original_set is not None and original_set.status == "GENERATED"
    detail = client.get(base + "/" + bundle["id"], headers=owner)
    assert detail.status_code == 200, detail.text
    assert {row[0] for row in detail.json()["rows"]} == {
        "BALANCE_SHEET",
        "INCOME_STATEMENT",
        "CASH_FLOW",
        "CHANGES_IN_EQUITY",
        "NOTES",
    }
    assert detail.json()["narratives"]
    run_id = None
    for format in ("CSV", "XLSX", "PDF"):
        report_run = request(client, writer, "/reports/generations", {**report, "format": format})
        assert report_run.status_code == 201 and report_run.json()["status"] == "COMPLETED", (
            report_run.text
        )
        assert report_run.json()["source_digest"] == bundle["snapshot_digest"]
        run_id = report_run.json()["id"]
        download = client.get(f"/reports/generations/{run_id}/download", headers=owner)
        assert (
            download.status_code == 200
            and sha256(download.content).hexdigest() == download.headers["X-Content-SHA256"]
        )
        if format == "CSV":
            text = download.content.decode()
            assert all(
                kind in text
                for kind in (
                    "BALANCE_SHEET",
                    "INCOME_STATEMENT",
                    "CASH_FLOW",
                    "CHANGES_IN_EQUITY",
                    "NOTES",
                )
            )
            assert bundle["id"] in text and approved.json()["id"] in text
        assert (
            client.get(
                f"/reports/generations/{run_id}/download",
                headers={**owner, "X-Company-ID": str(uuid4())},
            ).status_code
            == 404
        )
    if not concurrent:
        from tests.integration.test_agent_reporting_tools import runtime_for

        runtime_for(client, connection, connection.engine)
    action_url = "/agent/actions/approved-set-export"
    target = {
        key: value for key, value in report.items() if key not in {"report_code", "period_preset"}
    }
    target.update(
        confirmed=True,
        approved_snapshot_id=bundle["id"],
        expected_version=approved.json()["version"],
        expected_review_digest=bundle["snapshot_digest"],
    )
    refused = request(client, writer, action_url, {**target, "confirmed": False})
    assert refused.status_code == 422, refused.text
    wrong = request(client, writer, action_url, {**target, "expected_review_digest": "0" * 64})
    assert wrong.status_code == 200 and wrong.json()["status"] == "FAILED", wrong.text
    key = str(uuid4())
    export = request(client, writer, action_url, target, key)
    assert export.status_code == 200 and export.json()["status"] == "COMPLETED", export.text
    assert export.json()["answer_source_digest"] == bundle["snapshot_digest"]
    replay = request(client, writer, action_url, target, key)
    assert replay.json()["answer_resource_id"] == export.json()["answer_resource_id"]
    artifact = client.get(
        f"/reports/generations/{export.json()['answer_resource_id']}/download", headers=owner
    )
    assert artifact.status_code == 200 and bundle["snapshot_digest"] in artifact.content.decode()
    return bundle, report, run_id
