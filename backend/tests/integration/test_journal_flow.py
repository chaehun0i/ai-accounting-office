"""거래에서 승인·확정까지 실제 DB/API를 연결합니다."""

from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.accounting.templates.infrastructure.seed import seed_default_coa
from app.companies.infrastructure.models import MembershipModel
from tests.integration.test_onboarding import setup


def prepare(client, auth_service):
    _, connection = auth_service
    with Session(connection, join_transaction_mode="create_savepoint") as seed:
        seed_default_coa(seed)
        seed.commit()
    owner, _ = setup(client)
    template = client.get("/account-templates", headers=owner).json()[0]
    response = client.post(
        "/accounting/initialize",
        headers=owner,
        json={"fiscal_year": 2026, "template_id": template["id"]},
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/auth/register",
        json={"email": "accountant@example.com", "password": "StrongPassword!2026"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    user = client.get("/auth/me", headers={"Authorization": "Bearer " + token}).json()
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        from datetime import UTC, datetime

        session.add(
            MembershipModel(
                id=uuid4(),
                company_id=UUID(owner["X-Company-ID"]),
                user_id=UUID(user["id"]),
                role_code="ACCOUNTANT",
                status="ACTIVE",
                joined_at=datetime.now(UTC),
                version=1,
            )
        )
        session.commit()
    writer = {**owner, "Authorization": "Bearer " + token}
    accounts = client.get("/accounts", headers=writer).json()
    accounts = [a for a in accounts if a["posting_allowed"]]
    period = client.get("/accounting/periods", headers=writer).json()[0]
    payload = {
        "accounting_period_id": period["id"],
        "entry_date": "2026-01-02",
        "description": "회계 테스트",
        "lines": [
            {"account_id": accounts[0]["id"], "debit_amount": "100.0000"},
            {"account_id": accounts[-1]["id"], "credit_amount": "100.0000"},
        ],
    }
    return owner, writer, payload, connection


def command(client, headers, journal, action, key=None, **values):
    return client.post(
        "/journals/" + journal["id"] + "/" + action,
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
        json={
            "expected_version": journal["version"],
            "reason": "회계 검토 완료",
            "approval_id": journal["approval_id"],
            **values,
        },
    )


def test_journal_draft_review_post(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    response = api_client.post("/journals", headers=writer, json=payload)
    assert response.status_code == 201, response.text
    journal = response.json()
    assert journal["total_debit"] == journal["total_credit"] == "100.0000"
    for action in ["submit", "request-review"]:
        response = command(api_client, writer, journal, action)
        assert response.status_code == 200, response.text
        journal = response.json()
    assert command(api_client, writer, journal, "approve").status_code == 403
    response = command(api_client, owner, journal, "approve")
    assert response.status_code == 200, response.text
    journal = response.json()
    key = str(uuid4())
    response = command(api_client, owner, journal, "post", key)
    assert response.status_code == 200, response.text
    posted = response.json()
    assert posted["status"] == "POSTED" and posted["journal_no"] == "J-2026-000001"
    assert command(api_client, owner, journal, "post", key).json()["id"] == posted["id"]
    assert command(api_client, owner, journal, "post").status_code == 409
    assert (
        api_client.patch(
            "/journals/" + posted["id"],
            headers=writer,
            json={**payload, "expected_version": posted["version"]},
        ).status_code
        == 409
    )

