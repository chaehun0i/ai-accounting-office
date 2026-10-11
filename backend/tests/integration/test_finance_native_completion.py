"""공식 청구 금액으로 파생한 완납과 대사 차이 시나리오입니다."""

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from tests.integration.test_finance_allocations import confirm, make_record, make_source
from tests.integration.test_finance_flow import allocate, finance_setup


@pytest.mark.parametrize("kind,sheet", [("AR", "Sales_Invoices"), ("AP", "Purchase_Invoices")])
def test_native_amount_completion_and_mismatch(api_client, auth_service, kind, sheet):
    root = Path(__file__).parents[1] / "fixtures/finance/native-2025-v1"
    with (root / f"{sheet}.csv").open(encoding="utf-8", newline="") as stream:
        invoice = next(csv.DictReader(stream))
    # 원본의 부분 정산 행을 변경하지 않고 별도 파생 시나리오로 완납을 검증합니다.
    original = Decimal(invoice["total_amount"].replace(",", ""))
    owner, writer, payload, accounts, cp, _ = finance_setup(api_client, auth_service)
    target = make_source(api_client, owner, writer, payload, accounts, cp, kind, original)
    targets = "receivables" if kind == "AR" else "payables"
    for amount in (original / 2, original / 2):
        path, record = make_record(api_client, owner, writer, payload, accounts, cp, kind, amount)
        report = api_client.get(
            f"/{targets}/reconciliation?as_of=2026-01-31", headers=writer
        ).json()
        assert report["status"] == "MISMATCH"
        assert Decimal(report["difference"]) == amount
        record = allocate(api_client, writer, path, record, [(target, amount)])
        response = confirm(api_client, writer, path, record)
        assert response.status_code == 200, response.text
        report = api_client.get(
            f"/{targets}/reconciliation?as_of=2026-01-31", headers=writer
        ).json()
        assert report["status"] == "MATCHED" and Decimal(report["difference"]) == 0
        target = api_client.get(
            f"/{targets}/{target['id']}?as_of=2026-01-31", headers=writer
        ).json()
    assert target["status"] == "SETTLED" and Decimal(target["outstanding_amount"]) == 0
    aging = api_client.get(f"/{targets}/aging?as_of=2026-01-31", headers=writer).json()
    assert Decimal(aging["total_outstanding"]) == 0
    assert aging["counterparties"] == {}
