"""Company policy changes invalidate current CF source without changing frozen history."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evidence.infrastructure.models import EvidenceModel
from tests.integration.test_cash_flow_indirect import classify, setup_rules
from tests.integration.test_cash_flow_snapshot import ready_snapshot
from tests.integration.test_closing_workflow import request, reviewer
from tests.integration.test_finance_flow import post_journal
from tests.integration.test_intake_api import upload
from tests.integration.test_journal_flow import prepare


def test_policy_version_changes_snapshot_digest_without_rewriting_old_snapshot(
    api_client, auth_service
):
    _, writer, payload, _, _ = ready_snapshot(api_client, auth_service)
    first = request(api_client, writer, "/cash-flow/generate", payload)
    assert first.status_code == 201, first.text
    old = first.json()
    period = next(
        row
        for row in api_client.get("/accounting/periods", headers=writer).json()
        if row["id"] == payload["period_id"]
    )
    policy = {
        "effective_from": period["start_date"],
        "interest_paid": "FINANCING",
        "interest_received": "INVESTING",
        "income_tax_paid": "OPERATING",
    }
    saved = api_client.post("/cash-flow/policies", headers=writer, json=policy)
    assert saved.status_code == 201, saved.text
    assert (
        api_client.post("/cash-flow/policies", headers=writer, json=policy).json() == saved.json()
    )
    assert api_client.get(f"/cash-flow/{old['id']}", headers=writer).json() == old
    assert (
        api_client.get(
            "/cash-flow/statements", headers=writer, params={"period_id": payload["period_id"]}
        ).status_code
        == 409
    )
    bridge = api_client.get(
        "/cash-flow/indirect-bridge", headers=writer, params={"period_id": payload["period_id"]}
    ).json()
    assert bridge["status"] == "READY", bridge
    assert bridge["mapping_digest"] != payload["mapping_digest"]
    refreshed = request(
        api_client,
        writer,
        "/cash-flow/generate",
        {key: bridge[key] for key in payload},
        str(uuid4()),
    )
    assert refreshed.status_code == 201, refreshed.text
    assert refreshed.json()["policy_version"] == 1
    assert refreshed.json()["snapshot_digest"] != old["snapshot_digest"]


def test_verified_non_cash_pair_is_disclosed_without_changing_cash_totals(api_client, auth_service):
    owner, writer, base, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    imported = upload(api_client, writer)
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        evidence = session.scalar(
            select(EvidenceModel).where(
                EvidenceModel.company_id == UUID(writer["X-Company-ID"]),
                EvidenceModel.storage_object_id == UUID(imported["storage_object_id"]),
            )
        )
        assert evidence is not None
        evidence_id = str(evidence.id)
    accounts = {
        row["account_name"]: row["id"] for row in api_client.get("/accounts", headers=writer).json()
    }
    journal_base = {
        "accounting_period_id": base["accounting_period_id"],
        "entry_date": base["entry_date"],
        "source_type": "MANUAL",
    }
    cash = post_journal(
        api_client,
        owner,
        writer,
        journal_base,
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "100.0000"},
            {"account_id": accounts["매출"], "credit_amount": "100.0000"},
        ],
    )
    non_cash = post_journal(
        api_client,
        owner,
        writer,
        {**journal_base, "evidence_ids": [evidence_id]},
        [
            {"account_id": accounts["감가상각비"], "debit_amount": "10.0000"},
            {"account_id": accounts["감가상각누계액"], "credit_amount": "10.0000"},
        ],
    )
    run = request(
        api_client, writer, "/closing-runs", {"accounting_period_id": base["accounting_period_id"]}
    )
    assert run.status_code == 201, run.text
    approval = request(
        api_client, review, f"/closing-runs/{run.json()['id']}/submit", {"reason": "월마감"}
    )
    assert approval.status_code == 200, approval.text
    assert (
        request(
            api_client,
            owner,
            f"/closing-approvals/{approval.json()['id']}/approve",
            {"reason": "확인"},
        ).status_code
        == 200
    )
    assert (
        request(
            api_client,
            owner,
            f"/closing-runs/{run.json()['id']}/close",
            {"approval_id": approval.json()["id"]},
        ).status_code
        == 200
    )
    roles = [
        ("매출", "OPERATING_RESULT", None),
        ("감가상각비", "NONCASH_PAIR", "감가상각누계액"),
        ("감가상각누계액", "EXCLUDED_BALANCE", None),
    ]
    mapped, period = setup_rules(api_client, writer, base["accounting_period_id"], roles)
    classify(api_client, writer, mapped, period, "매출")
    statement_set = request(
        api_client,
        writer,
        "/financial-statements/generate",
        {"period_id": base["accounting_period_id"]},
    )
    assert statement_set.status_code == 201, statement_set.text
    lines = {row["account_id"]: row["id"] for row in non_cash["lines"]}
    disclosure = {
        "journal_id": non_cash["id"],
        "debit_line_id": lines[accounts["감가상각비"]],
        "credit_line_id": lines[accounts["감가상각누계액"]],
        "evidence_id": evidence_id,
        "source_type": "OTHER_VERIFIED",
        "amount": "10.0000",
    }
    created = api_client.post("/cash-flow/non-cash-disclosures", headers=writer, json=disclosure)
    assert created.status_code == 201, created.text
    assert (
        api_client.post("/cash-flow/non-cash-disclosures", headers=writer, json=disclosure).json()
        == created.json()
    )
    assert (
        api_client.post(
            "/cash-flow/non-cash-disclosures",
            headers=writer,
            json={**disclosure, "amount": "11.0000"},
        ).status_code
        == 409
    )
    assert (
        api_client.post(
            "/cash-flow/non-cash-disclosures",
            headers=writer,
            json={**disclosure, "journal_id": cash["id"]},
        ).status_code
        == 422
    )
    bridge = api_client.get(
        "/cash-flow/indirect-bridge",
        headers=writer,
        params={"period_id": base["accounting_period_id"]},
    ).json()
    assert bridge["status"] == "READY", bridge
    snapshot = request(
        api_client,
        writer,
        "/cash-flow/generate",
        {
            key: bridge[key]
            for key in (
                "period_id",
                "statement_set_id",
                "close_version",
                "source_digest",
                "mapping_digest",
            )
        },
    )
    assert snapshot.status_code == 201, snapshot.text
    assert snapshot.json()["net_operating"] == "100.0000"
    stored = api_client.get(f"/cash-flow/{snapshot.json()['id']}/disclosures", headers=writer)
    assert stored.status_code == 200 and stored.json() == [created.json()]
    assert api_client.get(
        "/cash-flow/non-cash-disclosures",
        headers=writer,
        params={"period_id": base["accounting_period_id"]},
    ).json() == [created.json()]
    report = api_client.post(
        "/reports/generations",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={
            "report_code": "CASH_FLOW",
            "format": "CSV",
            "period_id": base["accounting_period_id"],
            "period_preset": "CUSTOM",
            "date_from": period["start_date"],
            "date_to": period["end_date"],
        },
    )
    assert report.status_code == 201, report.text
    exported = api_client.get(
        f"/reports/generations/{report.json()['id']}/download", headers=writer
    )
    assert exported.status_code == 200
    assert "\nNonCashDisclosure\nsource_type,amount,journal_id,evidence_id\n" in (
        exported.content.decode("utf-8")
    )
    assert f"OTHER_VERIFIED,10.0000,{non_cash['id']},{evidence_id}" in (
        exported.content.decode("utf-8")
    )


def test_verified_disposal_gain_and_proceeds_reconcile_separately(api_client, auth_service):
    owner, writer, base, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    imported = upload(api_client, writer)
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        evidence = session.scalar(
            select(EvidenceModel).where(
                EvidenceModel.company_id == UUID(writer["X-Company-ID"]),
                EvidenceModel.storage_object_id == UUID(imported["storage_object_id"]),
            )
        )
        assert evidence is not None
        evidence_id = str(evidence.id)
    accounts = {
        row["account_name"]: row["id"] for row in api_client.get("/accounts", headers=writer).json()
    }
    journal_base = {
        "accounting_period_id": base["accounting_period_id"],
        "entry_date": base["entry_date"],
        "source_type": "MANUAL",
        "evidence_ids": [evidence_id],
    }
    acquired = post_journal(
        api_client,
        owner,
        writer,
        journal_base,
        [
            {"account_id": accounts["유형자산"], "debit_amount": "100.0000"},
            {"account_id": accounts["자본금"], "credit_amount": "100.0000"},
        ],
    )
    sold = post_journal(
        api_client,
        owner,
        writer,
        journal_base,
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "120.0000"},
            {"account_id": accounts["유형자산"], "credit_amount": "100.0000"},
            {"account_id": accounts["기타수익"], "credit_amount": "20.0000"},
        ],
    )
    close = request(
        api_client, writer, "/closing-runs", {"accounting_period_id": base["accounting_period_id"]}
    )
    assert close.status_code == 201, close.text
    approval = request(
        api_client, review, f"/closing-runs/{close.json()['id']}/submit", {"reason": "월마감"}
    )
    assert approval.status_code == 200, approval.text
    assert (
        request(
            api_client,
            owner,
            f"/closing-approvals/{approval.json()['id']}/approve",
            {"reason": "확인"},
        ).status_code
        == 200
    )
    assert (
        request(
            api_client,
            owner,
            f"/closing-runs/{close.json()['id']}/close",
            {"approval_id": approval.json()["id"]},
        ).status_code
        == 200
    )
    mapped, period = setup_rules(
        api_client,
        writer,
        base["accounting_period_id"],
        [
            ("유형자산", "EXCLUDED_BALANCE", None),
            ("자본금", "EXCLUDED_BALANCE", None),
            ("기타수익", "DISPOSAL_GAIN", "유형자산"),
        ],
    )
    for name in ("유형자산", "기타수익"):
        response = api_client.post(
            "/cash-flow/classifications",
            headers=writer,
            json={
                "account_id": mapped[name],
                "activity_type": "INVESTING",
                "line_code": "ASSET_DISPOSAL_PROCEEDS",
                "effective_from": period["start_date"],
            },
        )
        assert response.status_code == 201, response.text
    original_lines = {row["account_id"]: row["id"] for row in acquired["lines"]}
    created = api_client.post(
        "/cash-flow/non-cash-disclosures",
        headers=writer,
        json={
            "journal_id": acquired["id"],
            "debit_line_id": original_lines[accounts["유형자산"]],
            "credit_line_id": original_lines[accounts["자본금"]],
            "evidence_id": evidence_id,
            "source_type": "EQUITY_CONTRIBUTION_IN_KIND",
            "amount": "100.0000",
        },
    )
    assert created.status_code == 201, created.text
    sold_lines = {row["account_id"]: row["id"] for row in sold["lines"]}
    cash_line = sold_lines[accounts["현금및현금성자산"]]
    for name, amount in (("유형자산", "100.0000"), ("기타수익", "20.0000")):
        allocation = api_client.post(
            "/cash-flow/allocations",
            headers=writer,
            json={
                "journal_id": sold["id"],
                "cash_line_id": cash_line,
                "counterpart_line_id": sold_lines[accounts[name]],
                "evidence_id": evidence_id,
                "amount": amount,
            },
        )
        assert allocation.status_code == 201, allocation.text
    source = api_client.post(
        "/cash-flow/disposal-sources",
        headers=writer,
        json={
            "journal_id": sold["id"],
            "cash_line_id": cash_line,
            "asset_line_id": sold_lines[accounts["유형자산"]],
            "gain_line_id": sold_lines[accounts["기타수익"]],
            "evidence_id": evidence_id,
        },
    )
    assert source.status_code == 201, source.text
    assert source.json()["proceeds"] == "120.0000"
    assert source.json()["gain_amount"] == "-20.0000"
    statement_set = request(
        api_client,
        writer,
        "/financial-statements/generate",
        {"period_id": base["accounting_period_id"]},
    )
    assert statement_set.status_code == 201, statement_set.text
    bridge = api_client.get(
        "/cash-flow/indirect-bridge",
        headers=writer,
        params={"period_id": base["accounting_period_id"]},
    ).json()
    assert bridge["status"] == "READY", bridge
    assert bridge["net_operating"] == "0.0000"
    assert (
        next(row for row in bridge["adjustments"] if row["adjustment_code"] == "DISPOSAL_GAIN")[
            "amount"
        ]
        == "-20.0000"
    )
    snapshot = request(
        api_client,
        writer,
        "/cash-flow/generate",
        {
            key: bridge[key]
            for key in (
                "period_id",
                "statement_set_id",
                "close_version",
                "source_digest",
                "mapping_digest",
            )
        },
    )
    assert snapshot.status_code == 201, snapshot.text
    assert snapshot.json()["net_investing"] == "120.0000"
    assert snapshot.json()["net_operating"] == "0.0000"
    assert api_client.get(
        f"/cash-flow/{snapshot.json()['id']}/disposals", headers=writer
    ).json() == [source.json()]
