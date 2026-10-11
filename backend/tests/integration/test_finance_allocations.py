"""다중 배분·미배분·실패 원자성을 실제 PostgreSQL에서 검증합니다."""

from decimal import Decimal
from uuid import uuid4

import pytest

from tests.integration.test_finance_flow import (
    allocate,
    create_settlement,
    finance_setup,
    post_journal,
    recognize,
)


def make_source(client, owner, writer, payload, accounts, cp, kind, amount):
    control = accounts["매출채권" if kind == "AR" else "매입채무"]
    other = accounts["매출" if kind == "AR" else "소모품비"]
    journal = post_journal(
        client,
        owner,
        writer,
        payload,
        [
            {
                "account_id": control,
                "counterparty_id": cp,
                "debit_amount" if kind == "AR" else "credit_amount": str(amount),
            },
            {"account_id": other, "credit_amount" if kind == "AR" else "debit_amount": str(amount)},
        ],
    )
    return recognize(client, writer, journal, kind)


def make_record(client, owner, writer, payload, accounts, cp, kind, amount, applied=None):
    control = accounts["매출채권" if kind == "AR" else "매입채무"]
    applied = amount if applied is None else applied
    lines = [
        {
            "account_id": accounts["보통예금"],
            "debit_amount" if kind == "AR" else "credit_amount": str(amount),
        }
    ]
    if applied:
        lines.append(
            {
                "account_id": control,
                "counterparty_id": cp,
                "credit_amount" if kind == "AR" else "debit_amount": str(applied),
            }
        )
    if amount > applied:
        lines.append(
            {
                "account_id": accounts["선수금" if kind == "AR" else "선급금"],
                "credit_amount" if kind == "AR" else "debit_amount": str(amount - applied),
            }
        )
    journal = post_journal(client, owner, writer, payload, lines)
    return create_settlement(client, writer, journal, kind, amount)


def confirm(client, writer, path, record, key=None):
    return client.post(
        f"/{path}/{record['id']}/confirm",
        headers={**writer, "Idempotency-Key": key or str(uuid4())},
        json={"expected_version": record["version"]},
    )


@pytest.mark.parametrize("kind", ["AR", "AP"])
def test_batch_and_unapplied(api_client, auth_service, kind):
    owner, writer, payload, accounts, cp, _ = finance_setup(api_client, auth_service)

    def source(amount):
        return make_source(api_client, owner, writer, payload, accounts, cp, kind, amount)

    def record(amount, applied=None):
        return make_record(api_client, owner, writer, payload, accounts, cp, kind, amount, applied)

    first, second = source(4000000), source(2000000)
    path, value = record(6000000)
    value = allocate(api_client, writer, path, value, [(first, 4000000), (second, 2000000)])
    result = confirm(api_client, writer, path, value)
    assert result.status_code == 200, result.text
    assert Decimal(result.json()["unapplied_amount"]) == 0
    targets = "receivables" if kind == "AR" else "payables"
    for target in (first, second):
        assert (
            api_client.get(f"/{targets}/{target['id']}?as_of=2026-01-31", headers=writer).json()[
                "status"
            ]
            == "SETTLED"
        )
    third = source(4000000)
    path, value = record(6000000, 4000000)
    value = allocate(api_client, writer, path, value, [(third, 4000000)])
    result = confirm(api_client, writer, path, value)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "UNAPPLIED"
    assert Decimal(result.json()["unapplied_amount"]) == 2000000
    assert confirm(api_client, writer, path, value).status_code == 409


@pytest.mark.parametrize("kind", ["AR", "AP"])
def test_many_records_one_target_and_stale(api_client, auth_service, kind):
    owner, writer, payload, accounts, cp, _ = finance_setup(api_client, auth_service)
    target = make_source(api_client, owner, writer, payload, accounts, cp, kind, 100)
    path, first = make_record(api_client, owner, writer, payload, accounts, cp, kind, 60)
    path, second = make_record(api_client, owner, writer, payload, accounts, cp, kind, 40)
    first = allocate(api_client, writer, path, first, [(target, 60)])
    second = allocate(api_client, writer, path, second, [(target, 40)])
    assert confirm(api_client, writer, path, first).status_code == 200
    response = confirm(api_client, writer, path, second)
    assert response.status_code == 409
    assert response.json()["code"] == "SETTLEMENT_TARGET_STALE"
    targets = "receivables" if kind == "AR" else "payables"
    target = api_client.get(f"/{targets}/{target['id']}?as_of=2026-01-31", headers=writer).json()
    second = allocate(api_client, writer, path, second, [(target, 40)])
    assert confirm(api_client, writer, path, second).status_code == 200
    assert (
        api_client.get(f"/{targets}/{target['id']}?as_of=2026-01-31", headers=writer).json()[
            "status"
        ]
        == "SETTLED"
    )


@pytest.mark.parametrize("kind", ["AR", "AP"])
def test_overallocation_and_rollback(api_client, auth_service, kind, monkeypatch):
    from app.finance.settlements.infrastructure.repository import SettlementRepository

    owner, writer, payload, accounts, cp, _ = finance_setup(api_client, auth_service)
    target = make_source(api_client, owner, writer, payload, accounts, cp, kind, 100)
    path, value = make_record(api_client, owner, writer, payload, accounts, cp, kind, 100)
    url = f"/{path}/{value['id']}/allocations"

    def request(amount, target_id=target["id"]):
        return api_client.post(
            url,
            headers={**writer, "Idempotency-Key": str(uuid4())},
            json={
                "expected_version": value["version"],
                "allocations": [
                    {
                        "target_id": target_id,
                        "expected_version": target["version"],
                        "allocated_amount": str(amount),
                    }
                ],
            },
        )

    assert request(101).status_code == 422
    assert request(1, str(uuid4())).status_code == 404
    value = allocate(api_client, writer, path, value, [(target, 100)])
    original = SettlementRepository.confirm

    def failure(self, record):
        original(self, record)
        raise RuntimeError("테스트 실패 주입")

    monkeypatch.setattr(SettlementRepository, "confirm", failure)
    failed = confirm(api_client, writer, path, value)
    assert failed.status_code == 500
    assert failed.json()["code"] == "INTERNAL_ERROR"
    assert "테스트 실패 주입" not in failed.text
    assert api_client.get(f"/{path}/{value['id']}", headers=writer).json()["status"] == "DRAFT"
    targets = "receivables" if kind == "AR" else "payables"
    unchanged = api_client.get(f"/{targets}/{target['id']}?as_of=2026-01-31", headers=writer).json()
    assert unchanged["version"] == target["version"]
    assert Decimal(unchanged["outstanding_amount"]) == 100
