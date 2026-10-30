"""CLOSED BS/IS to frozen SCE, provenance and company isolation."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.reporting.equity.models import EquityStatementModel
from tests.integration.test_closing_workflow import request, reviewer
from tests.integration.test_finance_flow import post_journal
from tests.integration.test_journal_flow import prepare


def close(client, owner, writer, review, period_id):
    run = request(client, writer, "/closing-runs", {"accounting_period_id": period_id})
    assert run.status_code == 201, run.text
    approval = request(
        client, review, f"/closing-runs/{run.json()['id']}/submit", {"reason": "월마감"}
    )
    assert approval.status_code == 200, approval.text
    assert (
        request(
            client, owner, f"/closing-approvals/{approval.json()['id']}/approve", {"reason": "확인"}
        ).status_code
        == 200
    )
    result = request(
        client,
        owner,
        f"/closing-runs/{run.json()['id']}/close",
        {"approval_id": approval.json()["id"]},
    )
    assert result.status_code == 200, result.text


def test_equity_rollforward_uses_prior_bs_and_current_is(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    periods = api_client.get("/closing/periods", headers=writer).json()
    january = next(p for p in periods if p["period_no"] == 1)
    february = next(p for p in periods if p["period_no"] == 2)
    accounts = {
        a["account_name"]: a["id"] for a in api_client.get("/accounts", headers=writer).json()
    }
    capital = post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": january["id"],
            "entry_date": "2026-01-02",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "200.0000"},
            {"account_id": accounts["자본금"], "credit_amount": "200.0000"},
        ],
    )
    post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": january["id"],
            "entry_date": "2026-01-03",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "100.0000"},
            {"account_id": accounts["매출"], "credit_amount": "100.0000"},
        ],
    )
    close(api_client, owner, writer, review, january["id"])
    assert (
        request(
            api_client, writer, "/financial-statements/generate", {"period_id": january["id"]}
        ).status_code
        == 201
    )
    post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": february["id"],
            "entry_date": "2026-02-03",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "50.0000"},
            {"account_id": accounts["매출"], "credit_amount": "50.0000"},
        ],
    )
    contribution = post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": february["id"],
            "entry_date": "2026-02-04",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "25.0000"},
            {"account_id": accounts["자본금"], "credit_amount": "25.0000"},
        ],
    )
    dividend = post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": february["id"],
            "entry_date": "2026-02-05",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["미처분이익잉여금"], "debit_amount": "10.0000"},
            {"account_id": accounts["미지급배당금"], "credit_amount": "10.0000"},
        ],
    )
    close(api_client, owner, writer, review, february["id"])
    assert (
        request(
            api_client, writer, "/financial-statements/generate", {"period_id": february["id"]}
        ).status_code
        == 201
    )
    retained = api_client.post(
        "/equity/components",
        headers=writer,
        json={
            "component_code": "RETAINED",
            "name": "이익잉여금",
            "component_type": "RETAINED_EARNINGS",
            "display_order": 2,
        },
    )
    assert retained.status_code == 201, retained.text
    contributed = api_client.post(
        "/equity/components",
        headers=writer,
        json={
            "component_code": "CAPITAL",
            "name": "납입자본",
            "component_type": "CONTRIBUTED_CAPITAL",
            "display_order": 1,
        },
    )
    assert contributed.status_code == 201, contributed.text
    blocked = api_client.get(
        "/equity/reconciliation", headers=owner, params={"period_id": february["id"]}
    )
    assert blocked.status_code == 200 and blocked.json()["status"] == "BLOCKED"
    assert "EQUITY_MAPPING_INCOMPLETE" in blocked.json()["issues"]
    mapped = api_client.post(
        "/equity/mappings",
        headers=writer,
        json={
            "component_id": contributed.json()["id"],
            "account_id": accounts["자본금"],
            "effective_from": "2026-01-01",
        },
    )
    assert mapped.status_code == 201, mapped.text
    retained_mapping = api_client.post(
        "/equity/mappings",
        headers=writer,
        json={
            "component_id": retained.json()["id"],
            "account_id": accounts["미처분이익잉여금"],
            "effective_from": "2026-01-01",
        },
    )
    assert retained_mapping.status_code == 201, retained_mapping.text
    unclassified = api_client.get(
        "/equity/reconciliation", headers=owner, params={"period_id": february["id"]}
    )
    assert "UNCLASSIFIED_EQUITY_SOURCE" in unclassified.json()["issues"]
    declared = api_client.post(
        "/equity/dividends",
        headers=writer,
        json={
            "resolution_date": "2026-02-04",
            "payable_date": "2026-03-10",
            "total_amount": "10.0000",
            "source_journal_id": dividend["id"],
        },
    )
    assert declared.status_code == 201, declared.text
    assert (
        api_client.get(f"/equity/dividends/{declared.json()['id']}/payments", headers=owner).json()
        == []
    )
    for journal, account_id, kind in [
        (contribution, accounts["자본금"], "CAPITAL_CONTRIBUTION"),
        (dividend, accounts["미처분이익잉여금"], "DIVIDEND"),
    ]:
        line_id = next(line["id"] for line in journal["lines"] if line["account_id"] == account_id)
        classified = api_client.post(
            "/equity/events", headers=writer, json={"journal_line_id": line_id, "event_type": kind}
        )
        assert classified.status_code == 201, classified.text
    ready = api_client.get(
        "/equity/reconciliation", headers=owner, params={"period_id": february["id"]}
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "READY", ready.json()
    assert Decimal(ready.json()["balance_sheet_equity"]) == Decimal("365")
    assert Decimal(ready.json()["income_statement_profit"]) == Decimal("50")
    assert Decimal(ready.json()["rollforward_equity"]) == Decimal("365")
    key = str(uuid4())
    generated = request(
        api_client, writer, "/equity/statements/generate", {"period_id": february["id"]}, key
    )
    assert generated.status_code == 201, generated.text
    replay = request(
        api_client, writer, "/equity/statements/generate", {"period_id": february["id"]}, key
    )
    assert replay.status_code == 201 and replay.json()["id"] == generated.json()["id"]
    detail = api_client.get(f"/equity/statements/{generated.json()['id']}", headers=owner)
    assert detail.status_code == 200
    lines = {(line["component_id"], line["movement_type"]): line for line in detail.json()["lines"]}
    assert Decimal(lines[(retained.json()["id"], "OPENING")]["amount"]) == Decimal("100")
    assert Decimal(lines[(retained.json()["id"], "PROFIT_OR_LOSS")]["amount"]) == Decimal("50")
    assert Decimal(lines[(contributed.json()["id"], "CLOSING")]["amount"]) == Decimal("225")
    assert Decimal(lines[(retained.json()["id"], "OWNER_TRANSACTIONS")]["amount"]) == Decimal("-10")
    opening_line = lines[(contributed.json()["id"], "OPENING")]
    sources = api_client.get(
        f"/equity/statements/{generated.json()['id']}/lines/{opening_line['id']}/sources",
        headers=owner,
    )
    assert sources.status_code == 200 and sources.json()[0]["journal_id"] == capital["id"]
    assert api_client.get(
        f"/equity/statements/{generated.json()['id']}",
        headers={**owner, "X-Company-ID": str(uuid4())},
    ).status_code in {403, 404}
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        with pytest.raises(IntegrityError):
            session.execute(update(EquityStatementModel)
                            .where(EquityStatementModel.id == UUID(generated.json()["id"]))
                            .values(status="RECONCILED"))
        session.rollback()
