"""Tax preparation remains company-scoped and cannot become filing-ready without rules."""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.accounting.templates.infrastructure.seed import seed_default_coa
from tests.integration.test_onboarding import setup


def test_profile_period_retry_and_blocked_preparation(api_client):
    registered = api_client.post(
        "/auth/register",
        json={"email": f"tax-{uuid4()}@example.com", "password": "StrongPassword!2026"},
    )
    assert registered.status_code == 201, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    created = api_client.post(
        "/companies",
        headers=headers,
        json={
            "company_name": "세무 준비 테스트",
            "business_number": "1234567890",
            "taxpayer_type": "CORPORATION",
            "opening_date": "2026-01-01",
            "address": "테스트 주소",
        },
    )
    assert created.status_code == 201, created.text
    headers["X-Company-ID"] = created.json()["id"]
    headers["Idempotency-Key"] = "tax-profile-1"
    profile = {
        "taxpayer_type": "CORPORATION",
        "tax_regime": "VAT_GENERAL",
        "effective_from": "2026-01-01",
        "source": "사업자 등록 자료",
    }
    first = api_client.post("/tax/profiles", headers=headers, json=profile)
    assert first.status_code == 201, first.text
    assert (
        api_client.post("/tax/profiles", headers=headers, json=profile).json()["id"]
        == first.json()["id"]
    )
    headers["Idempotency-Key"] = "tax-period-1"
    period = api_client.post(
        "/tax/periods",
        headers=headers,
        json={"tax_type": "VAT", "period_start": "2026-01-01", "period_end": "2026-01-31"},
    )
    assert period.status_code == 201, period.text
    result = api_client.get(f"/tax/periods/{period.json()['id']}/preparation", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["ready_to_file"] is False
    assert {check["code"] for check in result.json()["checks"]} >= {
        "RULES_UNVERIFIED",
        "REVIEW_REQUIRED",
    }

    second = api_client.post(
        "/companies",
        headers=headers,
        json={
            "company_name": "다른 회사",
            "business_number": "9876543210",
            "taxpayer_type": "CORPORATION",
            "opening_date": "2026-01-01",
            "address": "테스트 주소",
        },
    )
    assert second.status_code == 201, second.text
    headers["X-Company-ID"] = second.json()["id"]
    assert (
        api_client.get(
            f"/tax/periods/{period.json()['id']}/preparation", headers=headers
        ).status_code
        == 404
    )


def test_vat_correction_keeps_only_latest_revision_in_preparation(api_client, auth_service):
    _, connection = auth_service
    with Session(connection, join_transaction_mode="create_savepoint") as seed:
        seed_default_coa(seed)
        seed.commit()
    headers, _ = setup(api_client)
    template = api_client.get("/account-templates", headers=headers).json()[0]
    initialized = api_client.post(
        "/accounting/initialize",
        headers=headers,
        json={"fiscal_year": 2026, "template_id": template["id"]},
    )
    assert initialized.status_code == 200, initialized.text
    transaction = api_client.post(
        "/transactions",
        headers=headers,
        json={
            "transaction_date": "2026-01-02",
            "accounting_date": "2026-01-02",
            "description": "매출",
            "amount": "110.0000",
            "direction": "INFLOW",
            "source_id": f"tax-sale-{uuid4()}",
        },
    )
    assert transaction.status_code == 201, transaction.text
    headers["Idempotency-Key"] = "vat-period"
    period = api_client.post(
        "/tax/periods",
        headers=headers,
        json={"tax_type": "VAT", "period_start": "2026-01-01", "period_end": "2026-01-31"},
    )
    assert period.status_code == 201, period.text
    path = f"/tax/periods/{period.json()['id']}/vat"
    payload = {
        "transaction_id": transaction.json()["id"],
        "tax_category": "TAXABLE",
        "supply_amount": "100.0000",
        "tax_amount": "10.0000",
        "deductible_status": "NOT_APPLICABLE",
        "reason_code": "SALE",
        "rule_reference": "수동 검토 대상",
    }
    headers["Idempotency-Key"] = "vat-fact-1"
    first = api_client.post(path, headers=headers, json=payload)
    assert first.status_code == 201, first.text
    assert api_client.post(path, headers=headers, json=payload).json()["id"] == first.json()["id"]
    headers["Idempotency-Key"] = "vat-fact-2"
    corrected = api_client.post(path, headers=headers, json={**payload, "reason_code": "CORRECTED"})
    assert corrected.status_code == 201, corrected.text
    assert corrected.json()["revision"] == 2
    preparation = api_client.get(f"/tax/periods/{period.json()['id']}/preparation", headers=headers)
    assert preparation.status_code == 200, preparation.text
    assert len(preparation.json()["vat_items"]) == 1
    assert preparation.json()["vat_items"][0]["id"] == corrected.json()["id"]
    assert preparation.json()["output_tax"] == "10.0000"
    assert preparation.json()["ready_to_file"] is False
