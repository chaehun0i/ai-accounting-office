"""SYN_MFG_001 native snapshot을 불변 adapter v1로 승격 경로에 통과시킵니다."""

import csv
import io
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.accounting.transactions.infrastructure.models import TransactionModel
from tests.integration.test_import_promotion import prepare, promote


def test_native_2025_transactions_exact_count_totals_and_replay(api_client, auth_service):
    headers, factory = prepare(api_client, auth_service)
    base = Path(__file__).parents[1] / "fixtures/finance/native-2025-v1"
    expected = {}
    for sheet, source, direction, count in [
        ("Sales_Invoices", "SALES", "INFLOW", 240),
        ("Purchase_Invoices", "PURCHASE", "OUTFLOW", 74),
    ]:
        with (base / f"{sheet}.csv").open(encoding="utf-8-sig", newline="") as f:
            records = list(csv.DictReader(f))
        assert len(records) == count
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "source_id",
                "transaction_date",
                "amount",
                "tax_amount",
                "currency",
                "counterparty_code",
            ]
        )
        total = Decimal(0)
        for row in records:
            amount = Decimal(row["total_amount"].replace(",", ""))
            total += amount
            writer.writerow(
                [
                    row["invoice_no"],
                    row["invoice_date"],
                    str(amount),
                    row["vat_amount"].replace(",", ""),
                    "KRW",
                    row["counterparty_code"],
                ]
            )
        uploaded = api_client.post(
            "/imports",
            headers=headers,
            data={"source_type": source, "source_system": "SYN_MFG_001_PROMOTION_V1"},
            files={"file": (f"{sheet}.csv", buffer.getvalue().encode(), "text/csv")},
        )
        assert uploaded.status_code == 201, uploaded.text
        from tests.integration.test_intake_api import confirm, preview

        value = uploaded.json()
        receipt = confirm(
            api_client, headers, value, preview(api_client, headers, value), f"confirm-{source}"
        ).json()
        result = promote(api_client, headers, value, receipt, f"promote-{source}")
        assert result.status_code == 200, result.text
        assert result.json()["transaction_count"] == count
        assert (
            promote(api_client, headers, value, receipt, f"promote-{source}").json()
            == result.json()
        )
        expected[direction] = total
    with factory.begin() as session:
        rows = list(session.scalars(select(TransactionModel)))
        assert len(rows) == 314 and len({(r.source_system, r.source_id) for r in rows}) == 314
        assert all(r.import_id and r.evidence_id for r in rows)
        for direction, total in expected.items():
            assert sum((r.amount for r in rows if r.direction == direction), Decimal(0)) == total
        assert expected == {"INFLOW": Decimal("740119600"), "OUTFLOW": Decimal("205330400")}
