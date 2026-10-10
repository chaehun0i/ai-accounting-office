"""권한·회사 경계·버전·불변성과 역분개를 실제 PostgreSQL에서 검증합니다."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.test_journal_flow import command, prepare


def create(client, writer, payload):
    response = client.post(
        "/journals", headers={**writer, "Idempotency-Key": str(uuid4())}, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def approved(client, owner, writer, journal):
    for actor, action in [(writer, "submit"), (writer, "request-review"), (owner, "approve")]:
        response = command(client, actor, journal, action)
        assert response.status_code == 200, response.text
        journal = response.json()
    return journal


def test_stale_balance_and_foreign_account(api_client, auth_service):
    owner, writer, payload, _ = prepare(api_client, auth_service)
    journal = create(api_client, writer, payload)
    assert command(api_client, writer, journal, "submit", expected_version=99).status_code == 409
    wrong = {
        **payload,
        "lines": [{**payload["lines"][0], "account_id": str(uuid4())}, payload["lines"][1]],
    }
    assert (
        api_client.post(
            "/journals", headers={**writer, "Idempotency-Key": str(uuid4())}, json=wrong
        ).status_code
        == 404
    )
    bad = {
        **payload,
        "lines": [payload["lines"][0], {**payload["lines"][1], "credit_amount": "99"}],
    }
    unbalanced = create(api_client, writer, bad)
    assert command(api_client, writer, unbalanced, "submit").status_code == 422
    assert (
        api_client.get(
            "/journals/" + journal["id"], headers={**writer, "X-Company-ID": str(uuid4())}
        ).status_code
        == 404
    )
    key = str(uuid4())
    first = api_client.post("/journals", headers={**writer, "Idempotency-Key": key}, json=payload)
    assert (
        api_client.post(
            "/journals", headers={**writer, "Idempotency-Key": key}, json=payload
        ).json()["id"]
        == first.json()["id"]
    )
    assert (
        api_client.post(
            "/journals",
            headers={**writer, "Idempotency-Key": key},
            json={**payload, "description": "다른 요청"},
        ).status_code
        == 409
    )


def test_closed_period_and_database_immutability(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    journal = approved(api_client, owner, writer, create(api_client, writer, payload))
    with connection.begin_nested():
        connection.execute(
            text("UPDATE accounting_periods SET status='CLOSED' WHERE id=:id"),
            {"id": payload["accounting_period_id"]},
        )
    assert command(api_client, owner, journal, "post").status_code == 409
    connection.execute(
        text("UPDATE accounting_periods SET status='OPEN' WHERE id=:id"),
        {"id": payload["accounting_period_id"]},
    )
    response = command(api_client, owner, journal, "post")
    assert response.status_code == 200, response.text
    posted = response.json()
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text("UPDATE journal_entries SET description='변경' WHERE id=:id"), {"id": posted["id"]}
        )
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text("DELETE FROM journal_lines WHERE journal_entry_id=:id"), {"id": posted["id"]}
        )
    reverse = command(api_client, owner, posted, "reverse", reversal_date="2026-01-03")
    assert reverse.status_code == 200, reverse.text
    reversal = reverse.json()
    assert reversal["status"] == "DRAFT"
    assert reversal["lines"][0]["credit_amount"] == posted["lines"][0]["debit_amount"]
    assert api_client.get("/journals/" + posted["id"], headers=owner).json()["status"] == "POSTED"
    assert (
        command(api_client, owner, posted, "reverse", reversal_date="2026-01-03").status_code == 409
    )

    for action in ("submit", "request-review"):
        response = command(api_client, writer, reversal, action)
        assert response.status_code == 200, response.text
        reversal = response.json()
    assert command(api_client, owner, reversal, "approve").status_code == 403
    params = {"company": owner["X-Company-ID"], "writer": posted["created_by"]}
    connection.execute(
        text(
            "UPDATE company_memberships SET role_code='REVIEWER' "
            "WHERE company_id=:company AND user_id=:writer"
        ),
        params,
    )
    response = command(api_client, writer, reversal, "approve")
    assert response.status_code == 200, response.text
    reversal = response.json()
    connection.execute(
        text(
            "UPDATE company_memberships SET status='REVOKED', revoked_at=now() "
            "WHERE company_id=:company AND user_id=:writer"
        ),
        params,
    )
    assert command(api_client, owner, reversal, "post").status_code == 403
    connection.execute(
        text(
            "UPDATE company_memberships SET status='ACTIVE', revoked_at=NULL "
            "WHERE company_id=:company AND user_id=:writer"
        ),
        params,
    )
    response = command(api_client, owner, reversal, "post")
    assert response.status_code == 200, response.text
    trial = api_client.get(
        "/trial-balance", headers=owner, params={"period_id": payload["accounting_period_id"]}
    )
    assert trial.status_code == 200, trial.text
    assert all(Decimal(r["ending_debit"]) == Decimal(r["ending_credit"]) == 0 for r in trial.json())


def test_posting_failure_rolls_back_number_and_approval(api_client, auth_service, monkeypatch):
    from app.accounting.sequences.infrastructure.repository import SequenceRepository

    owner, writer, payload, _ = prepare(api_client, auth_service)
    journal = approved(api_client, owner, writer, create(api_client, writer, payload))
    allocate = SequenceRepository.allocate

    def failure(self, *args, **kwargs):
        allocate(self, *args, **kwargs)
        raise RuntimeError("검증용 실패")

    monkeypatch.setattr(SequenceRepository, "allocate", failure)
    response = command(api_client, owner, journal, "post")
    assert response.status_code == 500
    current = api_client.get("/journals/" + journal["id"], headers=owner).json()
    assert current["status"] == "APPROVED" and current["version"] == journal["version"]
    monkeypatch.setattr(SequenceRepository, "allocate", allocate)
    posted = command(api_client, owner, journal, "post")
    assert posted.status_code == 200, posted.text
    assert posted.json()["journal_no"] == "J-2026-000001"
