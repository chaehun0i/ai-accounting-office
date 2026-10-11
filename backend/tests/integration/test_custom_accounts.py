"""사용자 계정과목은 회사에만 속하고 초기화로 사라지지 않습니다."""

from datetime import date

import pytest

from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict

pytest_plugins = ("tests.integration.test_accounting_master_service",)


def test_custom_accounts_company_scope_and_repeat_initialize(master):
    principal, first, accounting, _, _, companies = master
    accounting.initialize(principal, first.id, fiscal_year=2026)
    second = companies.create(
        principal,
        company_name="격리 회사",
        business_number="2234567890",
        taxpayer_type="INDIVIDUAL",
        opening_date=date(2026, 1, 1),
        address="합성 주소",
    ).company
    custom = accounting.create_account(
        principal,
        first.id,
        account_code="CUSTOM_001",
        account_name="온라인 판매수수료",
        account_type="EXPENSE",
    )
    assert custom.template_account_id is None and custom.normal_balance == "DEBIT"
    assert custom in accounting.accounts(principal, first.id)
    assert custom not in accounting.accounts(principal, second.id)
    other = accounting.create_account(
        principal,
        second.id,
        account_code="CUSTOM_001",
        account_name="다른 회사 계정",
        account_type="EXPENSE",
    )
    assert other.id != custom.id
    with pytest.raises(ResourceNotFound):
        accounting.create_account(
            principal,
            first.id,
            account_code="CUSTOM_002",
            account_name="타 회사 부모",
            account_type="EXPENSE",
            parent_account_id=other.id,
        )
    with pytest.raises(StateConflict):
        accounting.create_account(
            principal,
            first.id,
            account_code="CUSTOM_001",
            account_name="중복",
            account_type="EXPENSE",
        )
    accounting.initialize(principal, first.id, fiscal_year=2026)
    assert custom in accounting.accounts(principal, first.id)
    with pytest.raises(InvalidInput):
        accounting.create_account(
            principal,
            first.id,
            account_code="bad space",
            account_name="잘못된 코드",
            account_type="EXPENSE",
        )


def test_custom_account_api_permission_and_extra_fields(api_client, auth_service):
    from tests.integration.test_journal_flow import prepare

    owner, writer, _, _ = prepare(api_client, auth_service)
    body = {
        "account_code": "TEAM_001",
        "account_name": "우리 회사 전용 계정",
        "account_type": "EXPENSE",
    }
    assert api_client.post("/accounts", json=body).status_code == 401
    response = api_client.post("/accounts", headers=writer, json=body)
    assert response.status_code == 201, response.text
    assert response.json()["template_account_id"] is None
    assert api_client.post("/accounts", headers=writer, json=body).status_code == 409
    assert (
        api_client.post(
            "/accounts", headers=writer, json={**body, "company_id": owner["X-Company-ID"]}
        ).status_code
        == 422
    )
    user = api_client.post(
        "/auth/register",
        json={"email": "isolated-catalog@example.com", "password": "StrongPassword!2026"},
    ).json()
    foreign = {**writer, "Authorization": "Bearer " + user["access_token"]}
    assert (
        api_client.post(
            "/accounts", headers=foreign, json={**body, "account_code": "TEAM_002"}
        ).status_code
        == 404
    )
    assert api_client.get("/accounts", headers=foreign).status_code == 404
    invite = api_client.post(
        f"/companies/{owner['X-Company-ID']}/invitations",
        headers=owner,
        json={"email": "isolated-catalog@example.com", "role_code": "VIEWER"},
    ).json()
    assert (
        api_client.post(
            "/invitations/" + invite["invite_token"] + "/accept", headers=foreign, json={}
        ).status_code
        == 200
    )
    assert api_client.get("/accounts", headers=foreign).status_code == 200
    assert (
        api_client.post(
            "/accounts", headers=foreign, json={**body, "account_code": "TEAM_002"}
        ).status_code
        == 403
    )
