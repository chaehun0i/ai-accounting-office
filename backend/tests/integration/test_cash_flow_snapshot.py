"""Reconciled snapshot lifecycle, frozen provenance, rollback, and company boundaries."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounting.journals.infrastructure.models import JournalLineModel, JournalModel
from app.companies.infrastructure.models import MembershipModel
from app.reporting.cash_flow.models import CashFlowClassificationModel
from app.reporting.cash_flow.snapshot_models import CashFlowEventModel, CashFlowStatementModel
from app.reporting.cash_flow.snapshot_repository import CashSnapshotRepository
from tests.integration.test_cash_flow_indirect import classify, setup_rules
from tests.integration.test_closing_workflow import request, reviewer
from tests.integration.test_finance_flow import post_journal
from tests.integration.test_financial_statements import closed_company
from tests.integration.test_journal_flow import command, prepare
from tests.integration.test_onboarding import save


def ready_snapshot(client, auth_service):
    owner, writer, period_id, _, journal, connection = closed_company(client, auth_service)
    accounts, period = setup_rules(client, writer, period_id, [("매출", "OPERATING_RESULT", None)])
    classify(client, writer, accounts, period, "매출")
    generated = request(client, writer, "/financial-statements/generate", {"period_id": period_id})
    assert generated.status_code == 201, generated.text
    bridge = client.get(
        "/cash-flow/indirect-bridge", headers=writer, params={"period_id": period_id}
    ).json()
    assert bridge["status"] == "READY", bridge
    payload = {
        k: bridge[k]
        for k in (
            "period_id",
            "statement_set_id",
            "close_version",
            "source_digest",
            "mapping_digest",
        )
    }
    return owner, writer, payload, journal, connection


def ledger(session, company):
    return (
        list(
            session.execute(
                select(JournalModel.id, JournalModel.status, JournalModel.version)
                .where(JournalModel.company_id == company)
                .order_by(JournalModel.id)
            )
        ),
        list(
            session.execute(
                select(
                    JournalLineModel.id,
                    JournalLineModel.debit_amount,
                    JournalLineModel.credit_amount,
                )
                .where(JournalLineModel.company_id == company)
                .order_by(JournalLineModel.id)
            )
        ),
    )


def test_generation_replay_frozen_reads_and_company_isolation(api_client, auth_service):
    owner, writer, payload, journal, connection = ready_snapshot(api_client, auth_service)
    company = UUID(writer["X-Company-ID"])
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        before = ledger(session, company)
    response = request(api_client, writer, "/cash-flow/generate", payload)
    assert response.status_code == 201, response.text
    snapshot = response.json()
    identifier = snapshot["id"]
    assert snapshot["status"] == "RECONCILED" and snapshot["method"] == "INDIRECT"
    assert Decimal(snapshot["opening_cash"]) + Decimal(snapshot["net_operating"]) == Decimal(
        snapshot["closing_cash"]
    )
    assert request(api_client, writer, "/cash-flow/generate", payload).json() == snapshot
    assert api_client.get(f"/cash-flow/{identifier}", headers=writer).json() == snapshot
    assert (
        api_client.get(
            "/financial-statements/cash-flow",
            headers=writer,
            params={"period_id": payload["period_id"]},
        ).json()
        == snapshot
    )
    lines = api_client.get(f"/cash-flow/{identifier}/lines", headers=writer).json()
    drill = api_client.get(f"/cash-flow/{identifier}/drilldown", headers=writer).json()
    assert drill["lines"] == lines
    assert drill["events"][0]["journal_id"] == journal["id"]
    assert drill["events"][0]["classification_version"] == 1
    assert drill["adjustments"][0]["rule_version"] == 1
    assert drill["adjustment_sources"][0]["journal_id"] == journal["id"]
    assert drill["journals"][0]["journal_id"] == journal["id"]
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        event = session.scalar(
            select(CashFlowEventModel).where(CashFlowEventModel.company_id == company)
        )
        drill_event = {
            column.name: getattr(event, column.name)
            for column in CashFlowEventModel.__table__.columns
        }
    drill_event.update(id=uuid4(), allocation_id=uuid4(), allocation_version=None)
    with (
        pytest.raises(IntegrityError) as invalid,
        Session(connection, join_transaction_mode="create_savepoint") as session,
    ):
        session.add(CashFlowEventModel(**drill_event))
        session.flush()
    assert invalid.value.orig.sqlstate == "23514"
    assert invalid.value.orig.diag.constraint_name == "ck_cash_flow_events_allocation"
    selected = next(line for line in lines if line["line_code"] == "NET_OPERATING")
    filtered = api_client.get(
        f"/cash-flow/{identifier}/drilldown", headers=writer, params={"line_id": selected["id"]}
    )
    assert filtered.status_code == 200 and len(filtered.json()["lines"]) == 1
    assert filtered.json()["events"] == drill["events"]
    assert (
        api_client.get(
            f"/cash-flow/{identifier}/drilldown", headers=writer, params={"line_id": str(uuid4())}
        ).status_code
        == 404
    )
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        assert ledger(session, company) == before
        assert session.scalar(select(func.count()).select_from(CashFlowStatementModel)) == 1
        classification = session.scalar(
            select(CashFlowClassificationModel).where(
                CashFlowClassificationModel.company_id == company
            )
        )
        classification.line_code = "LATER_MAPPING"
        classification.version += 1
        session.commit()
    assert api_client.get(f"/cash-flow/{identifier}", headers=writer).json() == snapshot
    assert api_client.get(f"/cash-flow/{identifier}/drilldown", headers=writer).json() == drill
    assert (
        api_client.get(
            "/financial-statements/cash-flow",
            headers=writer,
            params={"period_id": payload["period_id"]},
        ).status_code
        == 409
    )
    assert request(api_client, writer, "/cash-flow/generate", payload).status_code == 409
    other = api_client.post(
        "/companies",
        headers=owner,
        json={
            "company_name": "CF isolated",
            "business_number": "9876543210",
            "taxpayer_type": "INDIVIDUAL",
            "opening_date": "2026-01-01",
            "address": "test",
        },
    )
    assert other.status_code == 201, other.text
    other_headers = {**owner, "X-Company-ID": other.json()["id"]}
    for suffix in ("", "/lines", "/drilldown"):
        assert (
            api_client.get(f"/cash-flow/{identifier}{suffix}", headers=other_headers).status_code
            == 404
        )
    assert request(api_client, other_headers, "/cash-flow/generate", payload).status_code == 404
    for table in (
        "cash_flow_statements",
        "cash_flow_lines",
        "cash_flow_events",
        "cash_flow_adjustments",
        "cash_flow_adjustment_sources",
        "cash_flow_journal_traces",
    ):
        with (
            pytest.raises(IntegrityError),
            Session(connection, join_transaction_mode="create_savepoint") as session,
        ):
            session.execute(text(f"UPDATE {table} SET id = id"))
        with (
            pytest.raises(IntegrityError),
            Session(connection, join_transaction_mode="create_savepoint") as session,
        ):
            session.execute(text(f"DELETE FROM {table}"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("close_version", 2),
        ("source_digest", "0" * 64),
        ("mapping_digest", "0" * 64),
        ("statement_set_id", str(uuid4())),
    ],
)
def test_stale_request_leaves_no_snapshot(api_client, auth_service, field, value):
    _, writer, payload, _, connection = ready_snapshot(api_client, auth_service)
    assert (
        request(api_client, writer, "/cash-flow/generate", {**payload, field: value}).status_code
        == 409
    )
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        assert session.scalar(select(func.count()).select_from(CashFlowStatementModel)) == 0


def test_incomplete_preflight_permission_and_atomic_retry(api_client, auth_service, monkeypatch):
    _, writer, payload, _, connection = ready_snapshot(api_client, auth_service)
    user = UUID(api_client.get("/auth/me", headers=writer).json()["id"])
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        member = session.scalar(
            select(MembershipModel).where(
                MembershipModel.user_id == user,
                MembershipModel.company_id == UUID(writer["X-Company-ID"]),
            )
        )
        member.role_code = "VIEWER"
        session.commit()
    assert request(api_client, writer, "/cash-flow/generate", payload).status_code == 403
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        member = session.scalar(
            select(MembershipModel).where(
                MembershipModel.user_id == user,
                MembershipModel.company_id == UUID(writer["X-Company-ID"]),
            )
        )
        member.role_code = "ACCOUNTANT"
        session.commit()
    original = CashSnapshotRepository.add

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated response failure before commit")

    with monkeypatch.context() as patch:
        patch.setattr(CashSnapshotRepository, "add", interrupted)
        assert request(api_client, writer, "/cash-flow/generate", payload).status_code == 500
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        assert session.scalar(select(func.count()).select_from(CashFlowStatementModel)) == 0
    assert request(api_client, writer, "/cash-flow/generate", payload).status_code == 201


def close_period(client, owner, writer, review, period_id):
    run = request(client, writer, "/closing-runs", {"accounting_period_id": period_id})
    assert run.status_code == 201, run.text
    approval = request(
        client, review, f"/closing-runs/{run.json()['id']}/submit", {"reason": "review"}
    )
    assert approval.status_code == 200, approval.text
    approved = request(
        client, owner, f"/closing-approvals/{approval.json()['id']}/approve", {"reason": "approve"}
    )
    assert approved.status_code == 200, approved.text
    closed = request(
        client,
        owner,
        f"/closing-runs/{run.json()['id']}/close",
        {"approval_id": approval.json()["id"]},
    )
    assert closed.status_code == 200, closed.text
    return run.json()["id"]


def test_current_stale_after_reopen_and_reclose_then_new_snapshot(api_client, auth_service):
    owner, writer, payload, _, _ = ready_snapshot(api_client, auth_service)
    generated = request(api_client, writer, "/cash-flow/generate", payload, "original-snapshot")
    assert generated.status_code == 201, generated.text
    old = generated.json()
    period_id = payload["period_id"]
    runs = api_client.get(f"/closing/periods/{period_id}/runs", headers=owner).json()
    run_id = runs[0]["id"]
    approval = request(
        api_client, writer, f"/closing-runs/{run_id}/reopen-request", {"reason": "correct"}
    )
    assert approval.status_code == 200, approval.text
    approved = request(
        api_client,
        owner,
        f"/closing-approvals/{approval.json()['id']}/approve",
        {"reason": "correct"},
    )
    assert approved.status_code == 200, approved.text
    reopened = request(
        api_client,
        owner,
        f"/closing-runs/{run_id}/reopen",
        {"approval_id": approval.json()["id"], "reason": "correct"},
    )
    assert reopened.status_code == 200, reopened.text
    assert (
        api_client.get(
            "/financial-statements/cash-flow", headers=writer, params={"period_id": period_id}
        ).status_code
        == 409
    )
    login = api_client.post(
        "/auth/login",
        json={"email": "reviewer-closing@example.com", "password": "StrongPassword!2026"},
    )
    assert login.status_code == 200, login.text
    review = {**owner, "Authorization": "Bearer " + login.json()["access_token"]}
    close_period(api_client, owner, writer, review, period_id)
    bs_is = request(api_client, writer, "/financial-statements/generate", {"period_id": period_id})
    assert bs_is.status_code == 201, bs_is.text
    assert (
        api_client.get(
            "/cash-flow/statements", headers=writer, params={"period_id": period_id}
        ).status_code
        == 409
    )
    bridge = api_client.get(
        "/cash-flow/indirect-bridge", headers=writer, params={"period_id": period_id}
    ).json()
    assert bridge["status"] == "READY", bridge
    fresh = {k: bridge[k] for k in payload}
    assert (
        request(api_client, writer, "/cash-flow/generate", fresh, "original-snapshot").status_code
        == 409
    )
    new = request(api_client, writer, "/cash-flow/generate", fresh)
    assert new.status_code == 201, new.text
    assert new.json()["id"] != old["id"] and new.json()["close_version"] > old["close_version"]
    assert api_client.get(f"/cash-flow/{old['id']}", headers=writer).json() == old


def test_opening_cash_sources_and_allocation_revision_stale_current(api_client, auth_service):
    from app.evidence.infrastructure.models import EvidenceModel
    from tests.integration.test_intake_api import upload

    owner, writer, payload, connection = prepare(api_client, auth_service)
    accounts = api_client.get("/accounts", headers=writer).json()
    cash = next(a for a in accounts if a["account_name"] == "현금및현금성자산")
    equity = next(a for a in accounts if a["account_type"] == "EQUITY" and a["posting_allowed"])
    values = [
        (f"Opening_Balances.{field}", f"2026-01-01|{account['account_code']}|", value)
        for account, debit, credit in ((cash, "50", "0"), (equity, "0", "50"))
        for field, value in (
            ("as_of_date", "2026-01-01"),
            ("account_code", account["account_code"]),
            ("debit_amount", debit),
            ("credit_amount", credit),
        )
    ]
    workspace = save(
        api_client, writer, api_client.get("/onboarding", headers=writer).json(), values
    )
    opening = request(
        api_client, writer, "/opening-balances/imports", {"expected_version": workspace["version"]}
    )
    assert opening.status_code == 201, opening.text
    opening = opening.json()
    for actor, action in (
        (writer, "submit"),
        (writer, "request-review"),
        (owner, "approve"),
        (owner, "post"),
    ):
        response = command(api_client, actor, opening, action)
        assert response.status_code == 200, response.text
        opening = response.json()
    imported = upload(api_client, writer)
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        evidence_id = session.scalar(
            select(EvidenceModel.id).where(
                EvidenceModel.company_id == UUID(writer["X-Company-ID"]),
                EvidenceModel.storage_object_id == UUID(imported["storage_object_id"]),
            )
        )
    ids = {a["account_name"]: a["id"] for a in accounts}
    journal = post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": payload["accounting_period_id"],
            "entry_date": payload["entry_date"],
            "source_type": "MANUAL",
            "evidence_ids": [str(evidence_id)],
        },
        [
            {"account_id": cash["id"], "debit_amount": "110"},
            {"account_id": ids["매출"], "credit_amount": "100"},
            {"account_id": ids["기타수익"], "credit_amount": "10"},
        ],
    )
    review = reviewer(api_client, owner, connection)
    period_id = payload["accounting_period_id"]
    close_period(api_client, owner, writer, review, period_id)
    _, period = setup_rules(
        api_client,
        writer,
        period_id,
        [("매출", "OPERATING_RESULT", None), ("기타수익", "OPERATING_RESULT", None)],
    )
    allocation = None
    for name, amount in (("매출", "100"), ("기타수익", "10")):
        classify(api_client, writer, ids, period, name)
        lines = {line["account_id"]: line["id"] for line in journal["lines"]}
        response = api_client.post(
            "/cash-flow/allocations",
            headers=writer,
            json={
                "journal_id": journal["id"],
                "cash_line_id": lines[cash["id"]],
                "counterpart_line_id": lines[ids[name]],
                "evidence_id": str(evidence_id),
                "amount": amount,
            },
        )
        assert response.status_code == 201, response.text
        if name == "매출":
            allocation = response.json()
    assert (
        request(
            api_client, writer, "/financial-statements/generate", {"period_id": period_id}
        ).status_code
        == 201
    )
    bridge = api_client.get(
        "/cash-flow/indirect-bridge", headers=writer, params={"period_id": period_id}
    ).json()
    assert bridge["status"] == "READY", bridge
    inputs = {
        k: bridge[k]
        for k in (
            "period_id",
            "statement_set_id",
            "close_version",
            "source_digest",
            "mapping_digest",
        )
    }
    generated = request(api_client, writer, "/cash-flow/generate", inputs)
    assert generated.status_code == 201, generated.text
    result = generated.json()
    assert Decimal(result["opening_cash"]) == 50 and Decimal(result["closing_cash"]) == 160
    drill = api_client.get(f"/cash-flow/{result['id']}/drilldown", headers=writer).json()
    opening_line = next(line for line in drill["lines"] if line["line_code"] == "OPENING_CASH")
    opening_drill = api_client.get(
        f"/cash-flow/{result['id']}/drilldown",
        headers=writer,
        params={"line_id": opening_line["id"]},
    ).json()
    assert {s["journal_id"] for s in opening_drill["cash_balance_sources"]} == {opening["id"]}
    assert all(s["is_opening"] for s in opening_drill["cash_balance_sources"])
    assert (
        sum(
            (Decimal(s["signed_debit_amount"]) for s in drill["cash_balance_sources"]), Decimal("0")
        )
        == 160
    )
    assert any(str(evidence_id) in trace["evidence_ids"] for trace in drill["journals"])
    revised = api_client.put(
        f"/cash-flow/allocations/{allocation['id']}",
        headers=writer,
        json={"amount": "90", "evidence_id": str(evidence_id)},
    )
    assert revised.status_code == 200, revised.text
    assert (
        api_client.get(
            "/cash-flow/statements", headers=writer, params={"period_id": period_id}
        ).status_code
        == 409
    )
    assert request(api_client, writer, "/cash-flow/generate", inputs).status_code == 409
    assert api_client.get(f"/cash-flow/{result['id']}/drilldown", headers=writer).json() == drill
