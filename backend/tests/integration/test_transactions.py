"""거래 API의 원천 중복과 회사 범위를 실제 PostgreSQL로 검증합니다."""

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session
from app.accounting.templates.infrastructure.seed import seed_default_coa

from app.companies.infrastructure.models import MembershipModel
from tests.integration.test_onboarding import setup


def test_transaction_api_source_and_isolation(api_client, auth_service):
    _, connection = auth_service
    with Session(connection, join_transaction_mode="create_savepoint") as seed:
        seed_default_coa(seed)
        seed.commit()
    headers, _ = setup(api_client)
    template = api_client.get("/account-templates", headers=headers).json()[0]
    result = api_client.post(
        "/accounting/initialize",
        headers=headers,
        json={
            "fiscal_year": 2026,
            "template_id": template["id"],
            "functional_currency_code": "KRW",
            "fiscal_year_start_month": 1,
        },
    )
    assert result.status_code == 200, result.text
    _, connection = auth_service
    connection.execute(
        update(MembershipModel)
        .where(MembershipModel.company_id == UUID(headers["X-Company-ID"]))
        .values(role_code="ACCOUNTANT")
    )
    payload = {
        "transaction_date": "2026-01-02",
        "accounting_date": "2026-01-02",
        "description": "제품 매출",
        "amount": "11000.0000",
        "direction": "INFLOW",
        "source_id": "sale-1",
    }
    created = api_client.post("/transactions", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["amount"] == "11000.0000"
    replay = api_client.post("/transactions", headers=headers, json=payload)
    assert replay.json()["id"] == row["id"]
    conflict = api_client.post(
        "/transactions", headers=headers, json={**payload, "amount": "12000"}
    )
    assert conflict.status_code == 409
    changed = api_client.patch(
        "/transactions/" + row["id"],
        headers=headers,
        json={"expected_version": 1, "description": "내용 수정"},
    )
    assert changed.status_code == 200, changed.text
    assert (
        api_client.patch(
            "/transactions/" + row["id"],
            headers=headers,
            json={"expected_version": 1, "description": "오래된 수정"},
        ).status_code
        == 409
    )
    other = {**headers, "X-Company-ID": "00000000-0000-0000-0000-000000000001"}
    assert api_client.get("/transactions/" + row["id"], headers=other).status_code == 404
    assert (
        api_client.post(
            "/transactions", headers=headers, json={**payload, "source_id": "float", "amount": 1.2}
        ).status_code
        == 422
    )
