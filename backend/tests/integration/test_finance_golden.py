"""GOLDEN_CORP_001의 기존 시산표 기대값과 보조부 잔액을 함께 비교합니다."""

from decimal import Decimal

from tests.integration.test_finance_allocations import confirm
from tests.integration.test_finance_flow import (
    allocate,
    create_settlement,
    finance_setup,
    post_journal,
)


def test_golden_corp_accounting_and_finance(api_client, auth_service):
    owner, writer, payload, accounts, customer, _ = finance_setup(api_client, auth_service)
    response = api_client.post(
        "/counterparties",
        headers=writer,
        json={
            "display_name": "SUPPLIER_B",
            "legal_name": "SUPPLIER_B",
            "roles": [{"role_code": "SUPPLIER", "effective_from": "2026-01-01"}],
        },
    )
    assert response.status_code == 201, response.text
    supplier = response.json()["id"]
    period = api_client.get("/accounting/periods", headers=writer).json()[9]
    payload = {**payload, "accounting_period_id": period["id"], "entry_date": "2026-10-01"}

    def entry(day, description, debits, credits):
        lines = []
        for direction, values in [("debit_amount", debits), ("credit_amount", credits)]:
            for name, amount, cp in values:
                lines.append(
                    {
                        "account_id": accounts["현금및현금성자산" if name == "현금" else name],
                        direction: str(amount),
                        "counterparty_id": cp,
                    }
                )
        return post_journal(
            api_client,
            owner,
            writer,
            {**payload, "entry_date": f"2026-10-{day:02d}"},
            lines,
            description,
        )

    entry(1, "기초 자본", [("현금", 50000000, None)], [("자본금", 50000000, None)])
    sale = entry(
        2,
        "T001 외상매출",
        [("매출채권", 11000000, customer)],
        [("매출", 10000000, None), ("부가세예수금", 1000000, None)],
    )
    entry(
        3,
        "T002 소프트웨어",
        [("소프트웨어비", 1000000, None), ("부가세대급금", 100000, None)],
        [("카드미지급금", 1100000, None)],
    )
    collection = entry(
        5, "T003 부분수금", [("현금", 5500000, None)], [("매출채권", 5500000, customer)]
    )
    purchase = entry(
        6,
        "T004 외상매입",
        [("소모품비", 3000000, None), ("부가세대급금", 300000, None)],
        [("매입채무", 3300000, supplier)],
    )
    payment = entry(
        7, "T005 부분지급", [("매입채무", 1650000, supplier)], [("현금", 1650000, None)]
    )
    entry(
        10,
        "T006 임차료",
        [("임차료", 2000000, None), ("부가세대급금", 200000, None)],
        [("현금", 2200000, None)],
    )
    entry(15, "T007 카드대금", [("카드미지급금", 1100000, None)], [("현금", 1100000, None)])
    for targets, source, settlement_journal, kind, amount, expected in [
        ("receivables", sale, collection, "AR", 5500000, 5500000),
        ("payables", purchase, payment, "AP", 1650000, 1650000),
    ]:
        response = api_client.post(
            f"/{targets}/from-journals",
            headers=writer,
            json={"journal_id": source["id"], "due_date": "2026-10-31"},
        )
        assert response.status_code == 200, response.text
        target = response.json()[0]
        path, record = create_settlement(api_client, writer, settlement_journal, kind, amount)
        record = allocate(api_client, writer, path, record, [(target, amount)])
        assert confirm(api_client, writer, path, record).status_code == 200
        report = api_client.get(
            f"/{targets}/reconciliation?as_of=2026-10-31", headers=writer
        ).json()
        assert report["status"] == "MATCHED"
        assert Decimal(report["subledger_amount"]) == expected
    trial = api_client.get("/trial-balance", headers=owner, params={"period_id": period["id"]})
    assert trial.status_code == 200, trial.text
    rows = trial.json()
    assert sum(Decimal(row["ending_debit"]) for row in rows) == Decimal("62650000")
    assert sum(Decimal(row["ending_credit"]) for row in rows) == Decimal("62650000")
    by_name = {row["account_name"]: row for row in rows}
    assert Decimal(by_name["현금및현금성자산"]["ending_balance"]) == Decimal("50550000")
    assert Decimal(by_name["카드미지급금"]["ending_balance"]) == 0
