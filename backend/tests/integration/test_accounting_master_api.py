from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, update
from sqlalchemy.orm import sessionmaker

from app.accounting.accounts.infrastructure.models import AccountChangeModel, AccountModel
from app.accounting.templates.domain.defaults import DEFAULT_ACCOUNTS
from app.accounting.templates.infrastructure.seed import seed_default_coa
from app.companies.infrastructure.models import MembershipModel

COMPANY = {
    "company_name": "회계 마스터 테스트",
    "business_number": "1234567890",
    "taxpayer_type": "CORPORATION",
    "opening_date": "2026-01-01",
    "address": "테스트 주소",
}


def setup(client):
    result = client.post(
        "/auth/register", json={"email": "master@example.com", "password": "StrongPassword!2026"}
    )
    assert result.status_code == 201, result.text
    headers = {"Authorization": f"Bearer {result.json()['access_token']}"}
    company = client.post("/companies", json=COMPANY, headers=headers)
    assert company.status_code == 201, company.text
    headers["X-Company-ID"] = company.json()["id"]
    return headers


def test_master_api_security_and_typed_contract(api_client, auth_service, caplog):
    client = api_client
    headers = setup(client)
    _, connection = auth_service
    factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    with factory.begin() as session:
        seed_default_coa(session)
    templates = client.get("/account-templates", headers=headers)
    assert templates.status_code == 200, templates.text
    payload = {"fiscal_year": 2026, "template_id": templates.json()[0]["id"]}
    assert client.post("/accounting/initialize", json=payload, headers=headers).status_code == 200
    assert len(client.get("/accounts", headers=headers).json()) == len(DEFAULT_ACCOUNTS)
    assert len(client.get("/accounting/periods", headers=headers).json()) == 12
    assert (
        client.patch(
            "/accounting/settings",
            json={"expected_version": 1, "allow_manual_journal": False},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/accounting/settings",
            json={"expected_version": 1, "allow_manual_journal": True},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        client.patch(
            "/accounting/settings",
            json={"expected_version": 2, "functional_currency_code": "USD"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/accounting/periods/" + str(uuid4()), json={"status": "CLOSED"}, headers=headers
        ).status_code
        == 404
    )
    assert client.get("/counterparties?arbitrary=secret", headers=headers).status_code == 422
    assert (
        client.post(
            "/counterparties",
            json={
                "display_name": "고객 A",
                "legal_name": "고객 A",
                "bank_refs": [
                    {"bank_code": "TEST", "account_alias": "계좌", "account_number": "1234567890"}
                ],
            },
            headers=headers,
        ).status_code
        == 422
    )
    token = f"vault:{uuid4()}"
    created = client.post(
        "/counterparties",
        json={
            "display_name": "고객 A",
            "legal_name": "고객 A",
            "business_number": "123-45-67890",
            "roles": [{"role_code": "CUSTOMER", "effective_from": "2026-01-01"}],
            "bank_refs": [
                {"bank_code": "TEST", "account_alias": "테스트 참조", "external_token": token}
            ],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["business_number"] == "*******890"
    resource = created.json()["id"]
    detail = client.get("/counterparties/" + resource, headers=headers)
    assert detail.status_code == 200, detail.text
    assert token not in detail.text and "external_token" not in detail.text
    assert token not in caplog.text and "123-45-67890" not in caplog.text
    assert detail.json()["roles"][0]["role_code"] == "CUSTOMER"
    assert (
        client.post(
            "/counterparties/" + resource + "/status",
            json={"expected_version": 1, "status": "BLOCKED"},
            headers=headers,
        ).status_code
        == 200
    )
    role_payload = {"expected_version": 2, "role_code": "SUPPLIER", "effective_from": "2026-01-01"}
    assert (
        client.post(
            "/counterparties/" + resource + "/roles", json=role_payload, headers=headers
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/counterparties/" + resource + "/roles", json=role_payload, headers=headers
        ).status_code
        == 409
    )
    foreign = {**headers, "X-Company-ID": str(uuid4())}
    assert client.get("/counterparties/" + resource, headers=foreign).status_code == 404
    assert (
        client.get("/accounts", headers={"Authorization": headers["Authorization"]}).status_code
        == 422
    )
    connection.execute(update(MembershipModel).values(status="REVOKED", revoked_at=func.now()))
    assert client.get("/accounts", headers=headers).status_code == 404


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("OWNER", True),
        ("ADMIN", True),
        ("ACCOUNTANT", False),
        ("REVIEWER", False),
        ("VIEWER", False),
    ],
)
def test_settings_rbac(api_client, auth_service, role, allowed):
    headers = setup(api_client)
    _, connection = auth_service
    connection.execute(update(MembershipModel).values(role_code=role))
    result = api_client.post(
        "/accounting/initialize",
        json={"fiscal_year": 2026, "template_id": str(uuid4())},
        headers=headers,
    )
    assert result.status_code == (422 if allowed else 403), result.text
    assert api_client.get("/accounts", headers=headers).status_code == 200


def test_company_account_update_deactivate_and_audit(api_client, auth_service):
    headers = setup(api_client)
    created = api_client.post(
        "/accounts",
        json={"account_code": "ZZ900", "account_name": "Temporary", "account_type": "ASSET"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    resource = created.json()["id"]
    assert created.json()["control_account_type"] is None
    update_url = f"/accounts/{resource}"
    changed = api_client.patch(
        update_url,
        json={"expected_version": 1, "account_code": "ZZ901", "account_name": "Updated"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert changed.json()["account_code"] == "ZZ901"
    assert (
        api_client.patch(
            update_url, json={"expected_version": 1, "account_name": "Stale"}, headers=headers
        ).status_code
        == 409
    )
    foreign = {**headers, "X-Company-ID": str(uuid4())}
    assert (
        api_client.patch(
            update_url, json={"expected_version": 2, "account_name": "Wrong"}, headers=foreign
        ).status_code
        == 404
    )
    deactivated = api_client.post(
        f"{update_url}/deactivate",
        json={"expected_version": 2, "reason": "No longer used"},
        headers=headers,
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["status"] == "INACTIVE"
    assert (
        api_client.post(
            f"{update_url}/deactivate",
            json={"expected_version": 3, "reason": "Again"},
            headers=headers,
        ).status_code
        == 409
    )
    _, connection = auth_service
    factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    with factory() as session:
        changes = (
            session.query(AccountChangeModel)
            .filter_by(account_id=UUID(resource))
            .order_by(AccountChangeModel.previous_version)
            .all()
        )
        assert [
            (change.action, change.previous_version, change.next_version) for change in changes
        ] == [("UPDATE", 1, 2), ("DEACTIVATE", 2, 3)]


def test_account_mutation_protects_template_references_and_control_role(api_client, auth_service):
    headers = setup(api_client)
    _, connection = auth_service
    factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    with factory.begin() as session:
        seed_default_coa(session)
    response = api_client.post(
        "/accounting/initialize", json={"fiscal_year": 2026}, headers=headers
    )
    assert response.status_code == 200, response.text
    template = api_client.get("/accounts", headers=headers).json()[0]
    assert template["template_account_id"] is not None
    assert (
        api_client.patch(
            f"/accounts/{template['id']}",
            json={"expected_version": template["version"], "account_name": "Changed"},
            headers=headers,
        ).status_code
        == 409
    )
    parent = api_client.post(
        "/accounts",
        json={"account_code": "ZZ800", "account_name": "Parent", "account_type": "ASSET"},
        headers=headers,
    ).json()
    child = api_client.post(
        "/accounts",
        json={
            "account_code": "ZZ801",
            "account_name": "Child",
            "account_type": "ASSET",
            "parent_account_id": parent["id"],
        },
        headers=headers,
    )
    assert child.status_code == 201, child.text
    assert (
        api_client.post(
            f"/accounts/{parent['id']}/deactivate",
            json={"expected_version": 1, "reason": "Referenced"},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        api_client.patch(
            f"/accounts/{parent['id']}",
            json={"expected_version": 1, "account_name": "New name"},
            headers=headers,
        ).status_code
        == 409
    )
    with factory.begin() as session:
        row = session.get(AccountModel, UUID(parent["id"]))
        assert row is not None
        row.control_account_type = "BANK_CASH"
    assert (
        api_client.patch(
            f"/accounts/{parent['id']}",
            json={"expected_version": 1, "account_code": "ZZ802"},
            headers=headers,
        ).status_code
        == 409
    )
