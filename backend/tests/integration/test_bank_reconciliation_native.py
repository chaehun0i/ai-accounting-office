"""세 산업 native 원본을 변형하지 않고 실제 Intake 원천 승격을 검증합니다."""

from decimal import Decimal
from time import perf_counter
from uuid import uuid4

import pytest

from tests.fixtures.reconciliation.adapter import canonical_csv, rows
from tests.integration.test_bank_reconciliation import command
from tests.integration.test_finance_flow import finance_setup
from tests.integration.test_intake_api import confirm, preview


@pytest.mark.parametrize(
    "industry,kind,expected",
    [
        ("service", "Bank", 3),
        ("retail", "Bank", 2),
        ("retail", "Card", 2),
        ("mfg", "Bank", 346),
        ("mfg", "Card", 88),
    ],
)
def test_native_financial_source_import(api_client, auth_service, industry, kind, expected):
    owner, writer, _, accounts, _, _ = finance_setup(api_client, auth_service)
    bank = kind == "Bank"
    account = api_client.post(
        "/bank-accounts" if bank else "/card-accounts",
        headers=owner,
        json={
            "institution_code": "FIXTURE",
            "alias": "합성 원천 검증",
            "usage_type": "MERCHANT" if not bank and industry == "retail" else "CORPORATE",
            "control_account_id": accounts[
                "보통예금" if bank else "미수금" if industry == "retail" else "카드미지급금"
            ],
        },
    )
    assert account.status_code == 201, account.text
    original = rows(industry, kind)
    year = 2025 if industry == "mfg" else 2026
    upload = api_client.post(
        "/imports",
        headers=writer,
        data={
            "source_type": "BANK_TRANSACTION" if bank else "CARD_TRANSACTION",
            "target_context": "BANK_SOURCE" if bank else "CARD_SOURCE",
            "source_system": f"NATIVE_{industry.upper()}_{kind.upper()}",
        },
        files={"file": ("source.csv", canonical_csv(industry, kind), "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    value = upload.json()
    draft = preview(api_client, writer, value)
    assert draft["valid"] and draft["row_count"] == expected, draft
    receipt = confirm(api_client, writer, value, draft).json()
    payload = {
        "account_id": account.json()["id"],
        "import_id": value["id"],
        "receipt_id": receipt["id"],
        "source_digest": receipt["source_digest"],
        "confirmed_version": receipt["confirmed_version"],
    }
    if bank:
        closing = sum(
            (
                Decimal(row["amount"]) if row["direction"] == "IN" else -Decimal(row["amount"])
                for row in original
            ),
            Decimal(0),
        )
        payload.update(
            statement_start=f"{year}-01-01",
            statement_end=f"{year}-12-31",
            opening_balance="0",
            closing_balance=str(closing),
        )
    path = "/bank-statements/imports" if bank else "/card-transactions/imports"
    key = str(uuid4())
    started = perf_counter()
    result = command(api_client, writer, path, payload, key)
    print(
        f"SOURCE_IMPORT_BENCHMARK {industry}/{kind} rows={expected} "
        f"seconds={perf_counter() - started:.3f}"
    )
    assert result.status_code == 200, result.text
    assert command(api_client, writer, path, payload, key).json() == result.json()
    assert command(api_client, writer, path, payload).json() == result.json()
    sources = api_client.get(
        f"/bank-statements/{result.json()['id']}/transactions"
        if bank
        else f"/card-transactions?account_id={account.json()['id']}",
        headers=writer,
    ).json()
    assert len(sources) == expected and len({source["source_id"] for source in sources}) == expected
    assert sum((Decimal(source["amount"]) for source in sources), Decimal(0)) == sum(
        (Decimal(row["amount"]) for row in original), Decimal(0)
    )
    assert all(
        source["source_import_id"] == value["id"] and Decimal(source["matched_amount"]) == 0
        for source in sources
    )
    assert {source["source_id"] for source in sources} == {row["source_id"] for row in original}

    if not bank:
        other = api_client.post(
            "/card-accounts",
            headers=owner,
            json={
                "institution_code": "FIXTURE",
                "alias": "다른 카드",
                "usage_type": "MERCHANT" if industry == "retail" else "CORPORATE",
                "control_account_id": accounts[
                    "부가세대급금" if industry == "retail" else "미지급금"
                ],
            },
        )
        assert other.status_code == 201, other.text
        duplicated = command(
            api_client,
            writer,
            path,
            {**payload, "account_id": other.json()["id"]},
        )
        assert duplicated.status_code == 409
        assert (
            api_client.get(
                f"/card-transactions?account_id={other.json()['id']}",
                headers=writer,
            ).json()
            == []
        )

    if industry != "mfg":
        # 산업별 원천의 입출금·환불 방향을 실제 거래와 연결하며 자동 분개하지 않습니다.
        for source in sources:
            transaction = command(
                api_client,
                writer,
                "/transactions",
                {
                    "transaction_date": source["occurred_at"][:10],
                    "accounting_date": source["occurred_at"][:10],
                    "description": source["description"] or "산업 원천 확인",
                    "amount": source["amount"],
                    "direction": "INFLOW" if source["direction"] == "IN" else "OUTFLOW",
                    "source_id": source["source_id"],
                },
            )
            assert transaction.status_code == 201, transaction.text
            path = (
                f"/bank-statements/{result.json()['id']}/match-candidates"
                if bank
                else f"/card-transactions/{source['id']}/match-candidates"
            )
            candidates = api_client.post(path, headers=writer)
            assert candidates.status_code == 200, candidates.text
            candidate = next(
                row
                for row in candidates.json()
                if row["source_id"] == source["id"] and row["target_id"] == transaction.json()["id"]
            )
            match = command(
                api_client,
                writer,
                "/reconciliations",
                {
                    "lines": [
                        {
                            "source_type": "BANK" if bank else "CARD",
                            "source_id": source["id"],
                            "target_type": "TRANSACTION",
                            "target_id": transaction.json()["id"],
                            "amount": source["amount"],
                            "source_version": candidate["source_version"],
                            "target_version": candidate["target_version"],
                        }
                    ]
                },
            )
            assert match.status_code == 201, match.text
            confirmed = command(
                api_client,
                writer,
                f"/reconciliations/{match.json()['id']}/confirm",
                {"expected_version": match.json()["version"]},
            )
            assert confirmed.status_code == 200, confirmed.text
        summary_path = (
            f"/bank-statements/{result.json()['id']}/summary"
            if bank
            else f"/card-accounts/{account.json()['id']}/summary?as_of={year}-12-31"
        )
        summary = api_client.get(summary_path, headers=writer).json()
        assert summary["unmatched_count"] == 0 and summary["partial_count"] == 0
        # 원천 대사는 회계 확정이 아니므로 아직 없는 GL 금액을 만들어내지 않습니다.
        assert Decimal(summary["gl_balance"]) == 0
