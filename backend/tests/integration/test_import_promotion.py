"""실제 업로드부터 거래 생성·재시도·롤백·회사 경계까지 검증합니다."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select, update

from app.accounting.settings.infrastructure.models import AccountingSettingsModel
from app.accounting.transactions.infrastructure.models import TransactionModel
from app.companies.infrastructure.models import MembershipModel
from app.intake.infrastructure.models import ImportReceiptModel
from app.intake.promotion.infrastructure.models import ImportPromotionRowModel
from tests.integration.test_intake_api import COMPANY, confirm, preview, setup, upload

CSV = (
    b"source_id,date,amount,currency,tax_amount,description\n"
    b"s1,2026-01-02,11000.0001,KRW,1000.0001,sale\n"
    b"s2,2026-01-03,22000,KRW,2000,second\n"
)


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
            .values(status="REVOKED", revoked_at=datetime.now(UTC))
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


def test_cross_source_collision_and_mapping_tamper(api_client, auth_service):
    headers, factory = prepare(api_client, auth_service)
    value, receipt = confirmed(api_client, headers)
    assert promote(api_client, headers, value, receipt).status_code == 200
    # source_type은 달라도 Transaction의 회사/원천시스템/원천ID 고유성은 유지됩니다.
    imported = api_client.post(
        "/imports",
        headers=headers,
        data={"source_type": "PURCHASE"},
        files={"file": ("purchase.csv", CSV, "text/csv")},
    ).json()
    draft = preview(api_client, headers, imported)
    other = confirm(api_client, headers, imported, draft, "purchase-confirm").json()
    result = promote(api_client, headers, imported, other, "purchase-promote")
    assert result.json()["code"] == "IMPORT_SOURCE_CONFLICT"
    with factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(TransactionModel)) == 2
    from app.intake.infrastructure.models import ImportMappingModel

    with factory.begin() as session:
        session.execute(
            update(ImportMappingModel)
            .where(
                ImportMappingModel.import_id == UUID(imported["id"]),
                ImportMappingModel.canonical_field_code == "description",
            )
            .values(canonical_field_code=None)
        )
    assert (
        promote(api_client, headers, imported, other, "tampered").json()["code"] == "PREVIEW_STALE"
    )


def test_file_tamper_requester_permission_and_csrf(api_client, auth_service):
    headers, factory = prepare(api_client, auth_service)
    value, receipt = confirmed(api_client, headers)
    payload = {
        "expected_version": receipt["confirmed_version"],
        "receipt_id": receipt["id"],
        "source_digest": receipt["source_digest"],
    }
    assert (
        api_client.post(
            f"/imports/{value['id']}/promote",
            headers={**headers, "Idempotency-Key": "csrf", "X-CSRF-Protection": "0"},
            json=payload,
        ).status_code
        == 403
    )
    service = api_client.app.state.services.intake
    storage = service.storage
    # 기존 저장소 계약의 안전한 키를 사용하되 디스크 파일을 변경한 상황을 재현합니다.
    monkey = __import__("unittest.mock", fromlist=["patch"])
    with monkey.patch.object(storage, "read", return_value=b"changed file"):
        assert promote(api_client, headers, value, receipt).json()["code"] == "PREVIEW_STALE"


def test_current_supported_limit_promotion_benchmark(api_client, auth_service):
    from time import perf_counter

    headers, factory = prepare(api_client, auth_service)
    content = (
        "source_id,date,amount,currency\n"
        + "".join(f"bench-{n},2026-01-02,1.0001,KRW\n" for n in range(1000))
    ).encode()
    value, receipt = confirmed(api_client, headers, content)
    started = perf_counter()
    result = promote(api_client, headers, value, receipt)
    elapsed = perf_counter() - started
    assert result.status_code == 200, result.text
    assert result.json()["transaction_count"] == 1000
    print(f"Promotion benchmark: rows=1000 seconds={elapsed:.3f}")


def test_xlsx_exact_promotion(api_client, auth_service):
    from app.intake.infrastructure.parser import XLSX_MIME
    from tests.unit.test_intake_parser import workbook

    headers, factory = prepare(api_client, auth_service)
    sheet = b'<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>source_id</t></is></c><c r="B1" t="inlineStr"><is><t>date</t></is></c><c r="C1" t="inlineStr"><is><t>amount</t></is></c><c r="D1" t="inlineStr"><is><t>currency</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>xlsx-1</t></is></c><c r="B2" t="inlineStr"><is><t>2026-01-02</t></is></c><c r="C2"><v>10.0001</v></c><c r="D2" t="inlineStr"><is><t>KRW</t></is></c></row></sheetData></worksheet>'  # noqa: E501
    value = api_client.post(
        "/imports",
        headers=headers,
        data={"source_type": "SALES"},
        files={"file": ("sales.xlsx", workbook({"xl/worksheets/sheet1.xml": sheet}), XLSX_MIME)},
    ).json()
    receipt = confirm(api_client, headers, value, preview(api_client, headers, value)).json()
    result = promote(api_client, headers, value, receipt)
    assert result.status_code == 200, result.text
    assert result.json()["rows"][0]["source_id"] == "xlsx-1"
    with factory.begin() as session:
        assert str(session.scalar(select(TransactionModel.amount))) == "10.0001"


def test_requester_and_transaction_permission_are_both_enforced(api_client, auth_service):
    headers, factory = prepare(api_client, auth_service)
    value, receipt = confirmed(api_client, headers)
    registration = api_client.post(
        "/auth/register",
        json={"email": "another-intake@example.com", "password": "StrongPassword!2026"},
    ).json()
    with factory.begin() as session:
        session.add(
            MembershipModel(
                company_id=UUID(headers["X-Company-ID"]),
                user_id=UUID(registration["user"]["id"]),
                role_code="ACCOUNTANT",
                status="ACTIVE",
                joined_at=datetime.now(UTC),
                version=1,
            )
        )
    other_headers = {**headers, "Authorization": "Bearer " + registration["access_token"]}
    assert promote(api_client, other_headers, value, receipt).status_code == 403
    with factory.begin() as session:
        session.execute(
            update(MembershipModel)
            .where(MembershipModel.company_id == UUID(headers["X-Company-ID"]))
            .values(role_code="VIEWER")
        )
    assert promote(api_client, headers, value, receipt).status_code == 403


def test_ambiguous_counterparty_is_not_guessed(api_client, auth_service):
    headers, factory = prepare(api_client, auth_service)
    content = b"source_id,date,amount,currency,counterparty\ns1,2026-01-02,100,KRW,ambiguous-name\n"
    value, receipt = confirmed(api_client, headers, content)
    result = promote(api_client, headers, value, receipt)
    assert result.status_code == 200, result.text
    assert result.json()["review_count"] == 1
    with factory.begin() as session:
        transaction = session.scalar(select(TransactionModel))
        assert transaction.counterparty_id is None and transaction.status == "NEEDS_INFORMATION"


def test_stale_confirmed_version_and_extra_input(api_client, auth_service):
    headers, factory = prepare(api_client, auth_service)
    value, receipt = confirmed(api_client, headers)
    assert (
        promote(api_client, headers, value, receipt, company_id=headers["X-Company-ID"]).status_code
        == 422
    )
    from app.intake.infrastructure.models import ImportModel

    with factory.begin() as session:
        session.execute(
            update(ImportModel)
            .where(ImportModel.id == UUID(value["id"]))
            .values(version=receipt["confirmed_version"] + 1)
        )
    assert promote(api_client, headers, value, receipt).json()["code"] == "PREVIEW_STALE"
