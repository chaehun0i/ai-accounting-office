"""CLOSED 장부 현금범위와 활동분류의 회사 격리·사전 점검."""

from decimal import Decimal
from uuid import uuid4

from tests.integration.test_financial_statements import closed_company


def test_cash_flow_preflight_requires_explicit_scope_and_classification(api_client, auth_service):
    owner, writer, period_id, _, journal, _ = closed_company(api_client, auth_service)
    accounts = {
        row["account_name"]: row["id"] for row in api_client.get("/accounts", headers=writer).json()
    }
    period = next(
        row
        for row in api_client.get("/accounting/periods", headers=writer).json()
        if row["id"] == period_id
    )
    query = {"period_id": period_id}
    missing = api_client.get("/cash-flow/preflight", headers=writer, params=query)
    assert missing.status_code == 200, missing.text
    assert missing.json()["ready"] is False
    assert missing.json()["issues"] == [{"code": "CASH_SCOPE_MISSING", "journal_id": None}]

    scope = {
        "account_id": accounts["현금및현금성자산"],
        "scope_type": "CASH",
        "effective_from": period["start_date"],
    }
    created = api_client.post("/cash-flow/cash-scope", headers=writer, json=scope)
    assert created.status_code == 201, created.text
    replay = api_client.post("/cash-flow/cash-scope", headers=writer, json=scope)
    assert replay.status_code == 201 and replay.json()["id"] == created.json()["id"]
    assert len(api_client.get("/cash-flow/cash-scope", headers=writer).json()) == 1
    unclassified = api_client.get("/cash-flow/preflight", headers=writer, params=query)
    assert unclassified.json()["issues"] == [
        {"code": "CASH_FLOW_UNCLASSIFIED", "journal_id": journal["id"]}
    ]

    classification = {
        "account_id": accounts["매출"],
        "activity_type": "OPERATING",
        "line_code": "CUSTOMER_RECEIPTS",
        "effective_from": period["start_date"],
    }
    mapped = api_client.post("/cash-flow/classifications", headers=writer, json=classification)
    assert mapped.status_code == 201, mapped.text
    ready = api_client.get("/cash-flow/preflight", headers=writer, params=query)
    assert ready.status_code == 200, ready.text
    value = ready.json()
    assert value["ready"] is True and value["issues"] == []
    assert Decimal(value["opening_cash"]) == Decimal("0")
    assert Decimal(value["closing_cash"]) == Decimal("100")
    assert Decimal(value["net_operating"]) == Decimal("100")
    assert value["classified_journal_count"] == 1
    assert value["source_digest"] and value["mapping_digest"]
    replayed = api_client.post("/cash-flow/classifications", headers=writer, json=classification)
    assert replayed.json()["id"] == mapped.json()["id"]

    changed = api_client.post(
        "/cash-flow/classifications",
        headers=writer,
        json={**classification, "activity_type": "FINANCING"},
    )
    assert changed.status_code == 409
    assert api_client.get(
        "/cash-flow/preflight",
        headers={**owner, "X-Company-ID": str(uuid4())},
        params=query,
    ).status_code in (403, 404)


def test_cash_scope_rejects_non_asset_account(api_client, auth_service):
    _, writer, period_id, _, _, _ = closed_company(api_client, auth_service)
    accounts = {
        row["account_name"]: row["id"] for row in api_client.get("/accounts", headers=writer).json()
    }
    period = next(
        row
        for row in api_client.get("/accounting/periods", headers=writer).json()
        if row["id"] == period_id
    )
    rejected = api_client.post(
        "/cash-flow/cash-scope",
        headers=writer,
        json={
            "account_id": accounts["매출"],
            "scope_type": "CASH",
            "effective_from": period["start_date"],
        },
    )
    assert rejected.status_code == 422
