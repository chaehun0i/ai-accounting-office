"""공식 native 원본의 금액을 변경하지 않고 업무문서 경로로 재현합니다."""

import csv
from decimal import Decimal
from pathlib import Path
from time import perf_counter

import pytest

from tests.integration.test_business_documents import body, create, transition
from tests.integration.test_finance_flow import finance_setup


@pytest.mark.parametrize(
    "fixture_path,source_code,counts,expected_totals",
    [
        ("finance/native-2025-v1", "SYN_MFG_001", (240, 74), ("781044000", "195277500")),
        ("invoices/native-service-v1", "SYN_SERVICE_001", (2, 1), ("8800000", "1100000")),
    ],
)
def test_native_documents_preserve_exact_source_facts(
    api_client, auth_service, record_property, fixture_path, source_code, counts, expected_totals
):
    owner, writer, _, _, _, _ = finance_setup(api_client, auth_service)
    base = Path(__file__).parents[1] / "fixtures" / fixture_path
    counterparties = {}
    started = perf_counter()
    totals = {}
    transactions = set()
    obligations = set()
    latencies = []
    for sheet, path, expected_count, expected_total in [
        ("Sales_Invoices", "/sales-invoices", counts[0], Decimal(expected_totals[0])),
        ("Purchase_Invoices", "/purchase-invoices", counts[1], Decimal(expected_totals[1])),
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
                    },
                )
                assert response.status_code == 201, response.text
                counterparties[code] = response.json()["id"]
            payload = body(
                counterparties[code],
                row["invoice_no"],
                row["supply_amount"].replace(",", ""),
                row["vat_amount"].replace(",", ""),
            )
            payload.update(
                issue_date=row["invoice_date"],
                accounting_date=row["invoice_date"],
                due_date=row["due_date"],
                source_system=source_code + "_DOCUMENT_ADAPTER_V1",
            )
            command_started = perf_counter()
            value = create(api_client, writer, path, payload)
            latencies.append(perf_counter() - command_started)
            response = transition(api_client, writer, path, value, "submit")
            assert response.status_code == 200, response.text
            submitted = response.json()
            command_started = perf_counter()
            response = transition(
                api_client, owner, path, submitted, "approve", "annual-" + row["invoice_no"]
            )
            latencies.append(perf_counter() - command_started)
            assert response.status_code == 200, response.text
            approved = response.json()
            assert Decimal(approved["total_amount"]) == Decimal(
                row["total_amount"].replace(",", "")
            )
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
    assert len(transactions) == len(obligations) == sum(counts)
    record_property(source_code + "_documents_seconds", round(perf_counter() - started, 3))
    record_property(
        source_code + "_command_p95_seconds",
        round(sorted(latencies)[max(0, len(latencies) * 95 // 100 - 1)], 3),
    )
    assert totals == {
        "Sales_Invoices": Decimal(expected_totals[0]),
        "Purchase_Invoices": Decimal(expected_totals[1]),
    }
