"""사람 승인 전표부터 부분 정산과 원장 대사까지 검증합니다."""

from decimal import Decimal
from uuid import uuid4

import pytest

from tests.integration.test_journal_flow import command, prepare


def post_journal(client, owner, writer, payload, lines, description="재무 보조부 검증"):
    response = client.post(
        "/journals",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={**payload, "description": description, "lines": lines},
    )
    assert response.status_code == 201, response.text
    journal = response.json()
    for actor, action in [
        (writer, "submit"),
        (writer, "request-review"),
        (owner, "approve"),
        (owner, "post"),
    ]:
        response = command(client, actor, journal, action)
        assert response.status_code == 200, response.text
        journal = response.json()
    return journal


def finance_setup(client, auth_service):
    owner, writer, payload, connection = prepare(client, auth_service)
    accounts = {a["account_name"]: a["id"] for a in client.get("/accounts", headers=writer).json()}
    response = client.post(
        "/counterparties",
        headers=writer,
        json={"display_name": "CUSTOMER_A", "legal_name": "CUSTOMER_A"},
    )
    assert response.status_code == 201, response.text
    return owner, writer, payload, accounts, response.json()["id"], connection


def recognize(client, writer, journal, kind):
    path = "receivables" if kind == "AR" else "payables"
    response = client.post(
        f"/{path}/from-journals",
        headers=writer,
        json={"journal_id": journal["id"], "due_date": "2026-01-20"},
    )
    assert response.status_code == 200, response.text
    assert (
        client.post(
            f"/{path}/from-journals",
            headers=writer,
            json={"journal_id": journal["id"], "due_date": "2026-01-20"},
        ).json()
        == response.json()
    )
    return response.json()[0]


def create_settlement(client, writer, journal, kind, amount):
    path = "collections" if kind == "AR" else "payments"
    key = str(uuid4())
    body = {
        "journal_id": journal["id"],
        "settlement_date": journal["entry_date"],
        "total_amount": str(amount),
    }
    response = client.post(f"/{path}", headers={**writer, "Idempotency-Key": key}, json=body)
    assert response.status_code == 201, response.text
    assert (
        client.post(f"/{path}", headers={**writer, "Idempotency-Key": key}, json=body).json()
        == response.json()
    )
    return path, response.json()


def allocate(client, writer, path, settlement, targets):
    body = {
        "expected_version": settlement["version"],
        "allocations": [
            {
                "target_id": target["id"],
                "expected_version": target["version"],
                "allocated_amount": str(amount),
            }
            for target, amount in targets
        ],
    }
    response = client.post(
        f"/{path}/{settlement['id']}/allocations",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    "kind,original,paid,control",
    [
        ("AR", "11000000", "5500000", "매출채권"),
        ("AP", "3300000", "1650000", "매입채무"),
    ],
)
def test_golden_partial_settlement(api_client, auth_service, kind, original, paid, control):
    owner, writer, payload, accounts, cp, connection = finance_setup(api_client, auth_service)
    source_lines = [
        {
            "account_id": accounts[control],
            "counterparty_id": cp,
            "debit_amount" if kind == "AR" else "credit_amount": original,
        },
        {
            "account_id": accounts["매출"] if kind == "AR" else accounts["소모품비"],
            "credit_amount" if kind == "AR" else "debit_amount": original,
        },
    ]
    source = post_journal(api_client, owner, writer, payload, source_lines)
    target = recognize(api_client, writer, source, kind)
    assert target["status"] == "OPEN"
    payment_lines = [
        {
            "account_id": accounts[control],
            "counterparty_id": cp,
            "credit_amount" if kind == "AR" else "debit_amount": paid,
        },
        {
            "account_id": accounts["보통예금"],
            "debit_amount" if kind == "AR" else "credit_amount": paid,
        },
    ]
    settlement_journal = post_journal(api_client, owner, writer, payload, payment_lines)
    path, settlement = create_settlement(api_client, writer, settlement_journal, kind, paid)
    settlement = allocate(api_client, writer, path, settlement, [(target, paid)])
    key = str(uuid4())
    body = {"expected_version": settlement["version"]}
    url = f"/{path}/{settlement['id']}/confirm"
    response = api_client.post(url, headers={**writer, "Idempotency-Key": key}, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CONFIRMED"
    assert (
        api_client.post(url, headers={**writer, "Idempotency-Key": key}, json=body).json()
        == response.json()
    )
    assert (
        api_client.post(
            url, headers={**writer, "Idempotency-Key": key}, json={"expected_version": 999}
        ).status_code
        == 409
    )
    targets = "receivables" if kind == "AR" else "payables"
    result = api_client.get(f"/{targets}/{target['id']}?as_of=2026-01-31", headers=writer).json()
    assert result["status"] == "PARTIAL"
    assert Decimal(result["outstanding_amount"]) == Decimal(original) - Decimal(paid)
    reconciliation = api_client.get(f"/{targets}/reconciliation?as_of=2026-01-31", headers=writer)
    assert reconciliation.status_code == 200, reconciliation.text
    assert reconciliation.json()["status"] == "MATCHED"
    assert Decimal(reconciliation.json()["subledger_amount"]) == Decimal(original) - Decimal(paid)
    assert (
        api_client.get(f"/{targets}/aging?as_of=2026-01-31", headers=writer).json()["overdue"]
        == result["outstanding_amount"]
    )
