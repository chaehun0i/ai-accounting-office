"""기초잔액 전표와 AR/AP Cutover 사전 대조 API를 검증합니다."""

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from tests.integration.test_journal_flow import command, prepare


def test_opening_draft_snapshot(api_client, auth_service):
    from tests.integration.test_onboarding import save

    owner, writer, payload, connection = prepare(api_client, auth_service)
    workspace = api_client.get("/onboarding", headers=writer).json()
    accounts = api_client.get("/accounts", headers=writer).json()
    codes = {a["id"]: a["account_code"] for a in accounts}
    updates = []
    for line in payload["lines"]:
        for field, value in {
            "as_of_date": "2026-01-01",
            "account_code": codes[line["account_id"]],
            "debit_amount": line.get("debit_amount", "0"),
            "credit_amount": line.get("credit_amount", "0"),
        }.items():
            updates.append(
                (
                    "Opening_Balances." + field,
                    "2026-01-01|" + codes[line["account_id"]] + "|",
                    value,
                )
            )
    workspace = save(api_client, writer, workspace, updates)
    headers = {**writer, "Idempotency-Key": "opening-test"}
    request = {"expected_version": workspace["version"]}
    response = api_client.post("/opening-balances/imports", headers=headers, json=request)
    assert response.status_code == 201, response.text
    journal = response.json()
    assert journal["source_type"] == "OPENING" and journal["status"] == "DRAFT"
    assert (
        api_client.post("/opening-balances/imports", headers=headers, json=request).json()["id"]
        == journal["id"]
    )
    workspace = save(
        api_client, writer, workspace, [("Company.company_name", "singleton", "수정된 회사명")]
    )
    response = api_client.post(
        "/opening-balances/imports",
        headers={**writer, "Idempotency-Key": "opening-unchanged-source"},
        json={"expected_version": workspace["version"]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["id"] == journal["id"]

    # 이전 버전에서 저장된 digest도 같은 기초잔액 원천이면 재사용할 수 있습니다.
    from app.accounting.opening_balances.infrastructure.models import OpeningImportModel
    from app.intake.domain.digest import digest

    with Session(connection, join_transaction_mode="create_savepoint") as session:
        opening = session.query(OpeningImportModel).filter_by(journal_id=UUID(journal["id"])).one()
        opening_cells = sorted(
            (cell["field_code"], cell["row_key"], str(cell["value"]))
            for cell in workspace["cells"]
            if cell["field_code"].startswith("Opening_Balances.")
        )
        opening.source_digest = digest({"version": opening.source_version, "cells": opening_cells})
        session.commit()
    workspace = save(
        api_client, writer, workspace, [("Company.company_name", "singleton", "다시 수정된 회사명")]
    )
    response = api_client.post(
        "/opening-balances/imports",
        headers={**writer, "Idempotency-Key": "opening-legacy-source"},
        json={"expected_version": workspace["version"]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["id"] == journal["id"]

    changed = save(
        api_client,
        writer,
        workspace,
        [("Opening_Balances.debit_amount", updates[2][1], "101")],
    )
    response = api_client.post(
        "/opening-balances/imports",
        headers={**writer, "Idempotency-Key": "opening-changed-source"},
        json={"expected_version": changed["version"]},
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "OPENING_SOURCE_CONFLICT"
    for action in ["submit", "request-review"]:
        response = command(api_client, writer, journal, action)
        assert response.status_code == 200, response.text
        journal = response.json()
    for action in ["approve", "post"]:
        response = command(api_client, owner, journal, action)
        assert response.status_code == 200, response.text
        journal = response.json()
    assert journal["status"] == "POSTED"


def test_ar_ap_cutover_preview_requires_current_company_draft(api_client, auth_service):
    from tests.integration.test_onboarding import save

    owner, writer, _, _ = prepare(api_client, auth_service)
    workspace = api_client.get("/onboarding", headers=writer).json()
    response = api_client.get(
        "/opening-balances/ar-ap-preview",
        headers=writer,
        params={"expected_version": workspace["version"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["session_version"] == workspace["version"]
    assert response.json()["ready"] is True
    assert response.json()["totals"] == []
    assert api_client.get(
        "/opening-balances/ar-ap-preview",
        headers={**writer, "X-Company-ID": str(uuid4())},
        params={"expected_version": workspace["version"]},
    ).status_code in (403, 404)
    assert (
        api_client.get(
            "/opening-balances/ar-ap-preview",
            headers=writer,
            params={"expected_version": workspace["version"] + 1},
        ).status_code
        == 409
    )
    mapping = next(
        value
        for value in api_client.get("/control-account-roles", headers=writer).json()
        if value["role"] == "AR"
    )
    account = next(
        value
        for value in api_client.get("/accounts", headers=writer).json()
        if value["id"] == mapping["account_id"]
    )
    workspace = save(
        api_client,
        writer,
        workspace,
        [
            ("AR_Opening.counterparty_code", "MISSING|INV-1", "MISSING"),
            ("AR_Opening.reference_code", "MISSING|INV-1", "INV-1"),
            ("AR_Opening.original_amount", "MISSING|INV-1", "100"),
            ("AR_Opening.due_date", "MISSING|INV-1", "2026-02-01"),
            ("AR_Opening.account_code", "MISSING|INV-1", account["account_code"]),
        ],
    )
    response = api_client.get(
        "/opening-balances/ar-ap-preview",
        headers=writer,
        params={"expected_version": workspace["version"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ready"] is False
    assert "UNKNOWN_COUNTERPARTY" in {item["code"] for item in response.json()["issues"]}
