"""공식 연간 청구서와 상세 행 금액의 연결을 Decimal로 검증합니다."""

import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "fixtures/finance/native-2025-v1"


def load(name):
    with (ROOT / f"{name}.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


@pytest.mark.parametrize("kind,count", [("Sales", 486), ("Purchase", 148)])
def test_native_invoice_line_totals(kind, count):
    lines = load(kind + "_Lines")
    assert len(lines) == count
    totals = defaultdict(lambda: Decimal(0))
    identities = set()
    for line in lines:
        identity = (line["invoice_no"], line["line_no"])
        assert identity not in identities
        identities.add(identity)
        totals[line["invoice_no"]] += Decimal(line["line_amount"].replace(",", ""))
    invoices = load(kind + "_Invoices")
    assert set(totals) == {invoice["invoice_no"] for invoice in invoices}
    for invoice in invoices:
        assert totals[invoice["invoice_no"]] == Decimal(invoice["supply_amount"].replace(",", ""))
