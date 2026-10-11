"""공식 native 원본의 금액을 변경하지 않고 업무문서 경로로 재현합니다."""

import csv
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from tests.integration.test_business_documents import body, create, transition
from tests.integration.test_finance_flow import finance_setup


def test_manufacturing_314_documents_preserve_exact_source_facts(
    api_client, auth_service, record_property
):
    owner, writer, _, _, _, _ = finance_setup(api_client, auth_service)
    base = Path(__file__).parents[1] / "fixtures/finance/native-2025-v1"
    counterparties = {}
    started = perf_counter()
    totals = {}
    transactions = set()
    obligations = set()
    for sheet, path, expected_count, expected_total in [
        ("Sales_Invoices", "/sales-invoices", 240, Decimal("781044000")),
        ("Purchase_Invoices", "/purchase-invoices", 74, Decimal("195277500")),
    ]:
        with (base / (sheet + ".csv")).open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        assert len(rows) == expected_count
        total = Decimal(0)
        for row in rows:
            code = row["counterparty_code"]
            if code not in counterparties:
                response = api_client.post(
                    "/counterparties",
                    headers=writer,
                    json={
                        "display_name": code,
                        "legal_name": code,
                        "counterparty_code": code,
                    },
                )
                assert response.status_code == 201, response.text
                counterparties[code] = response.json()["id"]
            payload = body(
                counterparties[code], row["invoice_no"], row["supply_amount"], row["vat_amount"]
            )
            payload.update(
                issue_date=row["invoice_date"],
                accounting_date=row["invoice_date"],
                due_date=row["due_date"],
                source_system="SYN_MFG_001_DOCUMENT_ADAPTER_V1",
            )
            value = create(api_client, writer, path, payload)
            response = transition(api_client, writer, path, value, "submit")
            assert response.status_code == 200, response.text
            submitted = response.json()
            response = transition(
                api_client, owner, path, submitted, "approve", "annual-" + row["invoice_no"]
            )
            assert response.status_code == 200, response.text
            approved = response.json()
            assert Decimal(approved["total_amount"]) == Decimal(row["total_amount"])
            total += Decimal(approved["total_amount"])
            transactions.add(approved["transaction_id"])
            obligations.add(approved["obligation_id"])
            assert (
                transition(
                    api_client, owner, path, submitted, "approve", "annual-" + row["invoice_no"]
                ).json()
                == approved
            )
        assert total == expected_total
        result = api_client.get(path, headers=writer)
        assert result.status_code == 200, result.text
        assert len(result.json()) == expected_count
        totals[sheet] = total
    assert len(transactions) == len(obligations) == 314
    record_property("documents_314_seconds", round(perf_counter() - started, 3))
    assert totals == {
        "Sales_Invoices": Decimal("781044000"),
        "Purchase_Invoices": Decimal("195277500"),
    }
