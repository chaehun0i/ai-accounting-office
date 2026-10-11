"""회사 격리·권한·입력 계약은 화면과 별개로 서버에서 강제합니다."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.companies.infrastructure.models import MembershipModel
from tests.integration.test_finance_allocations import make_record, make_source
from tests.integration.test_finance_flow import allocate, finance_setup


def test_finance_company_and_permissions(api_client, auth_service):
    owner, writer, payload, accounts, cp, connection = finance_setup(api_client, auth_service)
    target = make_source(api_client, owner, writer, payload, accounts, cp, "AR", 100)
    path, record = make_record(api_client, owner, writer, payload, accounts, cp, "AR", 100)
    assert api_client.get("/receivables?as_of=2026-01-31").status_code == 401
    assert api_client.get("/receivables?as_of=2026-01-31", headers=owner).status_code == 403
    assert (
        api_client.post(
            f"/{path}/{record['id']}/confirm",
            headers={**owner, "Idempotency-Key": str(uuid4())},
            json={"expected_version": record["version"]},
        ).status_code
        == 403
    )
    response = api_client.post(
        "/companies",
        headers=owner,
        json={
            "company_name": "다른 회사",
            "business_number": "2222222222",
            "corporation_number": "2222222222222",
            "taxpayer_type": "CORPORATION",
            "opening_date": "2025-01-01",
            "address": "테스트 주소",
        },
    )
    assert response.status_code == 201, response.text
    other_company = response.json()["id"]
    actor = api_client.app.state.services.auth.authenticate(
        writer["Authorization"].removeprefix("Bearer ")
    )
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        session.add(
            MembershipModel(
                id=uuid4(),
                company_id=UUID(other_company),
                user_id=actor.user_id,
                role_code="ACCOUNTANT",
                status="ACTIVE",
                joined_at=datetime.now(UTC),
                version=1,
            )
        )
        session.commit()
    foreign = {**writer, "X-Company-ID": other_company}
    for url in [f"/receivables/{target['id']}?as_of=2026-01-31", f"/collections/{record['id']}"]:
        response = api_client.get(url, headers=foreign)
        assert response.status_code == 404 and response.json()["code"] == "RESOURCE_NOT_FOUND"
    response = api_client.post(
        f"/collections/{record['id']}/allocations",
        headers={**foreign, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": record["version"],
            "allocations": [
                {
                    "target_id": target["id"],
                    "expected_version": target["version"],
                    "allocated_amount": "100",
                }
            ],
        },
    )
    assert response.status_code == 404
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        membership = session.scalar(
            select(MembershipModel).where(
                MembershipModel.company_id == UUID(writer["X-Company-ID"]),
                MembershipModel.user_id == actor.user_id,
            )
        )
        membership.status = "REVOKED"
        membership.revoked_at = datetime.now(UTC)
        session.commit()
    assert api_client.get("/receivables?as_of=2026-01-31", headers=writer).status_code == 404


def test_finance_extra_float_and_posted_source_contract(api_client, auth_service):
    owner, writer, payload, accounts, cp, _ = finance_setup(api_client, auth_service)
    response = api_client.post(
        "/journals", headers={**writer, "Idempotency-Key": str(uuid4())}, json=payload
    )
    assert response.status_code == 201, response.text
    journal = response.json()
    response = api_client.post(
        "/receivables/from-journals",
        headers=writer,
        json={"journal_id": journal["id"], "due_date": "2026-01-31"},
    )
    assert response.status_code == 409 and response.json()["code"] == "JOURNAL_NOT_POSTED"
    response = api_client.post(
        "/collections",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={"journal_id": journal["id"], "settlement_date": "2026-01-02", "total_amount": 1.1},
    )
    assert response.status_code == 422
    response = api_client.post(
        "/collections",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={
            "journal_id": journal["id"],
            "settlement_date": "2026-01-02",
            "total_amount": "100",
            "status": "CONFIRMED",
        },
    )
    assert response.status_code == 422
    target = make_source(api_client, owner, writer, payload, accounts, cp, "AR", 100)
    path, record = make_record(api_client, owner, writer, payload, accounts, cp, "AR", 200)
    response = api_client.post(
        f"/{path}/{record['id']}/allocations",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": record["version"],
            "allocations": [
                {
                    "target_id": target["id"],
                    "expected_version": target["version"],
                    "allocated_amount": "101",
                }
            ],
        },
    )
    assert (
        response.status_code == 422 and response.json()["code"] == "SETTLEMENT_ALLOCATION_EXCEEDED"
    )
    record = allocate(api_client, writer, path, record, [(target, 100)])
    response = api_client.post(
        f"/{path}/{record['id']}/confirm",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={"expected_version": record["version"]},
    )
    assert response.status_code == 409 and response.json()["code"] == "SETTLEMENT_JOURNAL_MISMATCH"
