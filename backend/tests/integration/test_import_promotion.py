"""실제 업로드부터 거래 생성·재시도·롤백·회사 경계까지 검증합니다."""

from uuid import UUID

import pytest
from sqlalchemy import func, select, update

from app.accounting.settings.infrastructure.models import AccountingSettingsModel
from app.accounting.transactions.infrastructure.models import TransactionModel
from app.companies.infrastructure.models import MembershipModel
from app.intake.infrastructure.models import ImportReceiptModel
from app.intake.promotion.infrastructure.models import ImportPromotionRowModel
from tests.integration.test_intake_api import COMPANY, confirm, preview, setup, upload

CSV = b"source_id,date,amount,currency,tax_amount,description\ns1,2026-01-02,11000.0001,KRW,1000.0001,sale\ns2,2026-01-03,22000,KRW,2000,second\n"


def prepare(client, auth_service):
    headers, factory = setup(client, auth_service)
    with factory.begin() as session:
        session.add(
            AccountingSettingsModel(
                company_id=UUID(headers["X-Company-ID"]),
                functional_currency_code="KRW",
                fiscal_year_start_month=1,
                journal_number_prefix="JE",
                numbering_reset_policy="FISCAL_YEAR",
                allow_manual_journal=True,
                accounting_framework_code="KR_GENERAL",
                framework_version="1",
                framework_effective_from=__import__("datetime").date(2026, 1, 1),
                inventory_cost_method="WEIGHTED_AVERAGE",
                depreciation_policy_code="STRAIGHT_LINE",
                reporting_taxonomy_code="KR_GENERAL",
                version=1,
            )
        )
    return headers, factory


def confirmed(client, headers, content=CSV, key="confirm"):
    value = upload(client, headers, content)
    receipt = confirm(client, headers, value, preview(client, headers, value), key)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["status"] == "CONFIRMED"
    return value, receipt.json()


def promote(client, headers, value, receipt, key="promote", **overrides):
    return client.post(
        f"/imports/{value['id']}/promote",
        headers={**headers, "Idempotency-Key": key},
        json={
            "expected_version": receipt["confirmed_version"],
            "receipt_id": receipt["id"],
            "source_digest": receipt["source_digest"],
            **overrides,
        },
    )


def test_exact_promotion_receipt_replay_and_provenance(api_client, auth_service):
    headers, factory = prepare(api_client, auth_service)
    value, receipt = confirmed(api_client, headers)
    result = promote(api_client, headers, value, receipt)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["transaction_count"] == 2 and data["status"] == "COMPLETED"
    assert len(data["rows"]) == 2 and data["failed_count"] == 0
    assert promote(api_client, headers, value, receipt).json() == data
    assert promote(api_client, headers, value, receipt, "another").json() == data
    assert (
        promote(api_client, headers, value, receipt, expected_version=999).json()["code"]
        == "IDEMPOTENCY_CONFLICT"
    )
    with factory.begin() as session:
        rows = list(session.scalars(select(TransactionModel).order_by(TransactionModel.source_id)))
        assert len(rows) == 2 and str(rows[0].amount) == "11000.0001"
        assert str(rows[0].tax_amount) == "1000.0001"
        assert rows[0].direction == "INFLOW" and rows[0].import_id == UUID(value["id"])
        assert rows[0].evidence_id and rows[0].source_system == "FILE_UPLOAD"
    other, other_receipt = confirmed(api_client, headers, key="other-confirm")
    reused = promote(api_client, headers, other, other_receipt, "other-promote")
    assert reused.status_code == 200, reused.text
    assert {r["status"] for r in reused.json()["rows"]} == {"REUSED"}
    assert api_client.get(f"/imports/{value['id']}/receipt", headers=headers).json() == data


def test_atomic_failure_and_retry(api_client, auth_service, monkeypatch):
    headers, factory = prepare(api_client, auth_service)
    value, receipt = confirmed(api_client, headers)
    from app.accounting.transactions.application.service import TransactionService

    original = TransactionService.save_in
    calls = []

    def fail(uow, actor, value, expected_version=None):
        calls.append(value.id)
        if len(calls) == 2:
            from app.contracts.access_errors import StateConflict

            raise StateConflict()
        return original(uow, actor, value, expected_version)

    monkeypatch.setattr(TransactionService, "save_in", staticmethod(fail))
    assert promote(api_client, headers, value, receipt).status_code == 409
    with factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(TransactionModel)) == 0
        assert session.scalar(select(func.count()).select_from(ImportPromotionRowModel)) == 0
        assert session.scalar(select(ImportReceiptModel.transaction_count)) == 0
    monkeypatch.setattr(TransactionService, "save_in", staticmethod(original))
    assert promote(api_client, headers, value, receipt).json()["transaction_count"] == 2


def test_security_stale_and_invalid_state(api_client, auth_service):
    headers, factory = prepare(api_client, auth_service)
    value, receipt = confirmed(api_client, headers)
    assert (
        promote(api_client, headers, value, receipt, source_digest="0" * 64).json()["code"]
        == "PREVIEW_STALE"
    )
    assert (
        api_client.post(f"/imports/{value['id']}/promote", headers=headers, json={}).status_code
        == 422
    )
    other = api_client.post(
        "/companies",
        headers=headers,
        json={**COMPANY, "company_name": "다른 회사", "business_number": "9876543210"},
    ).json()
    assert promote(
        api_client, {**headers, "X-Company-ID": other["id"]}, value, receipt
    ).status_code in (403, 404)
    with factory.begin() as session:
        session.execute(
            update(MembershipModel)
            .where(MembershipModel.company_id == UUID(headers["X-Company-ID"]))
            .values(status="REVOKED")
        )
    assert promote(api_client, headers, value, receipt).status_code == 403


@pytest.mark.parametrize("changed", [b"USD", b"-1"])
def test_invalid_economic_fact_leaves_no_transactions(api_client, auth_service, changed):
    headers, factory = prepare(api_client, auth_service)
    content = (
        CSV.replace(b"KRW", changed) if changed == b"USD" else CSV.replace(b"11000.0001", changed)
    )
    value, receipt = confirmed(api_client, headers, content)
    assert promote(api_client, headers, value, receipt).status_code == 422
    with factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(TransactionModel)) == 0
