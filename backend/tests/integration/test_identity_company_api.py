from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.companies.infrastructure.models import InvitationModel, MembershipModel
from app.identity.users.infrastructure.models import UserModel

PASSWORD = "correct horse battery staple"
COMPANY = {
    "company_name": "한빛 회계",
    "business_number": "1234567890",
    "taxpayer_type": "CORPORATION",
    "opening_date": "2025-01-01",
    "address": "서울",
}


def register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    assert "refresh_token" not in response.json()
    assert "HttpOnly" in response.headers["set-cookie"]
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_auth_api_recovery_and_logout(api_client: TestClient) -> None:
    client = api_client
    headers = register(client, "person@example.com")
    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert (
        client.post(
            "/auth/login", json={"email": "person@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login",
            json={"email": "person@example.com", "password": PASSWORD, "role": "OWNER"},
        ).status_code
        == 422
    )
    original = client.cookies.get("aao-refresh")
    recovered = client.post("/auth/refresh")
    assert recovered.status_code == 200
    headers = {"Authorization": f"Bearer {recovered.json()['access_token']}"}
    assert client.cookies.get("aao-refresh") != original
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert not client.cookies.get("aao-refresh")
    assert client.get("/auth/me", headers=headers).status_code == 401
    login = client.post("/auth/login", json={"email": "person@example.com", "password": PASSWORD})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post("/auth/logout-all", headers=headers).status_code == 200
    assert client.post("/auth/refresh").status_code == 401


@pytest.mark.parametrize("status", ["DISABLED", "REVOKED"])
def test_disabled_users_are_blocked(api_client: TestClient, auth_service, status: str) -> None:
    headers = register(api_client, "person@example.com")
    _, connection = auth_service
    connection.execute(update(UserModel).values(status=status))
    assert api_client.get("/auth/me", headers=headers).status_code == 401
    assert (
        api_client.post(
            "/auth/login", json={"email": "person@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert api_client.post("/auth/refresh").status_code == 401


def test_csrf_and_rate_limit(api_client: TestClient) -> None:
    client = api_client
    assert (
        client.post(
            "/auth/login",
            json={"email": "person@example.com", "password": PASSWORD},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    client.headers.pop("X-CSRF-Protection")
    assert client.post("/auth/refresh").status_code == 403
    client.headers["X-CSRF-Protection"] = "1"
    for _ in range(10):
        assert (
            client.post(
                "/auth/login", json={"email": "unknown@example.com", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/auth/login", json={"email": "unknown@example.com", "password": "wrong"}
        ).status_code
        == 429
    )


@pytest.mark.parametrize(
    "role,expected",
    [
        ("OWNER", 200),
        ("ADMIN", 200),
        ("ACCOUNTANT", 403),
        ("REVIEWER", 403),
        ("VIEWER", 403),
        ("AUDITOR", 403),
        ("TAX_ACCOUNTANT", 403),
        ("TAX_REVIEWER", 403),
    ],
)
def test_company_permissions_and_cross_company(
    api_client: TestClient, auth_service, role: str, expected: int
) -> None:
    client = api_client
    owner = register(client, "owner@example.com")
    created = client.post("/companies", headers=owner, json=COMPANY)
    assert created.status_code == 201, created.text
    company = created.json()
    company_id = company["id"]
    assert company["role_code"] == "OWNER"
    assert "company.update" in company["permissions"]
    other = register(client, "other@example.com")
    assert client.get(f"/companies/{company_id}", headers=other).status_code == 404
    assert (
        client.patch(
            f"/companies/{company_id}",
            headers=other,
            json={"expected_version": 1, "company_name": "다른 회사"},
        ).status_code
        == 404
    )
    assert client.get("/companies", headers=other).json() == []
    assert client.get(f"/companies/{uuid4()}", headers=owner).status_code == 404
    _, connection = auth_service
    connection.execute(update(MembershipModel).values(role_code=role))
    updated = client.patch(
        f"/companies/{company_id}",
        headers=owner,
        json={"expected_version": 1, "company_name": "새 이름"},
    )
    assert updated.status_code == expected, updated.text
    if expected == 200:
        assert updated.json()["version"] == 2
        assert (
            client.patch(
                f"/companies/{company_id}",
                headers=owner,
                json={"expected_version": 1, "address": "부산"},
            ).status_code
            == 409
        )
    assert client.get(f"/companies/{company_id}", headers=owner).status_code == 200
    assert len(client.get("/companies", headers=owner).json()) == 1
    connection.execute(
        update(MembershipModel).values(
            status="REVOKED",
            revoked_at=datetime.now(UTC),
        )
    )
    assert client.get(f"/companies/{company_id}", headers=owner).status_code == 404
    assert client.get("/companies", headers=owner).json() == []


def test_invitation_lifecycle_and_company_switch(api_client: TestClient, auth_service) -> None:
    client = api_client
    owner = register(client, "owner@example.com")
    first = client.post("/companies", headers=owner, json=COMPANY).json()
    second = client.post(
        "/companies", headers=owner, json={**COMPANY, "company_name": "두 번째 회사"}
    ).json()
    assert len(client.get("/companies", headers=owner).json()) == 2
    invited = client.post(
        f"/companies/{first['id']}/invitations",
        headers=owner,
        json={"email": "member@example.com", "role_code": "VIEWER"},
    )
    assert invited.status_code == 201, invited.text
    token = invited.json()["invite_token"]
    assert (
        client.post(
            f"/companies/{first['id']}/invitations",
            headers=owner,
            json={"email": "member@example.com", "role_code": "ADMIN"},
        ).status_code
        == 409
    )
    wrong = register(client, "wrong@example.com")
    assert client.post(f"/invitations/{token}/accept", headers=wrong).status_code == 404
    member = register(client, "member@example.com")
    accepted = client.post(f"/invitations/{token}/accept", headers=member)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role_code"] == "VIEWER"
    assert client.post(f"/invitations/{token}/accept", headers=member).status_code == 409
    assert client.get(f"/companies/{second['id']}", headers=member).status_code == 404
    assert len(client.get("/companies", headers=member).json()) == 1
    _, connection = auth_service
    assert token not in connection.scalars(select(InvitationModel.invite_token_hash)).all()
    revoked = client.post(
        f"/companies/{second['id']}/invitations",
        headers=owner,
        json={"email": "member@example.com", "role_code": "ACCOUNTANT"},
    ).json()
    assert (
        client.delete(
            f"/companies/{first['id']}/invitations/{revoked['id']}", headers=owner
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/companies/{second['id']}/invitations/{revoked['id']}", headers=owner
        ).status_code
        == 200
    )
    assert (
        client.post(f"/invitations/{revoked['invite_token']}/accept", headers=member).status_code
        == 409
    )
    expired = client.post(
        f"/companies/{second['id']}/invitations",
        headers=owner,
        json={"email": "member@example.com", "role_code": "ACCOUNTANT"},
    ).json()
    row = (
        connection.execute(
            select(InvitationModel.__table__).where(InvitationModel.id == UUID(expired["id"]))
        )
        .mappings()
        .one()
    )
    connection.execute(
        update(InvitationModel)
        .where(InvitationModel.id == row["id"])
        .values(
            created_at=row["created_at"] - timedelta(days=8),
            expires_at=row["created_at"] - timedelta(days=1),
        )
    )
    assert (
        client.post(f"/invitations/{expired['invite_token']}/accept", headers=member).status_code
        == 409
    )


def test_company_creation_rolls_back_without_owner_role(
    api_client: TestClient, auth_service
) -> None:
    from sqlalchemy import delete, func

    from app.companies.infrastructure.models import (
        CompanyModel,
        RoleModel,
        RolePermissionModel,
        TenantModel,
    )

    headers = register(api_client, "atomic@example.com")
    _, connection = auth_service
    connection.execute(delete(RolePermissionModel).where(RolePermissionModel.role_code == "OWNER"))
    connection.execute(delete(RoleModel).where(RoleModel.code == "OWNER"))
    response = api_client.post("/companies", json=COMPANY, headers=headers)
    assert response.status_code == 422
    assert response.json()["code"] == "BUSINESS_RULE_VIOLATION"
    assert connection.scalar(select(func.count()).select_from(CompanyModel)) == 0
    assert connection.scalar(select(func.count()).select_from(TenantModel)) == 0


def test_permission_changes_are_enforced_from_database(
    api_client: TestClient, auth_service
) -> None:
    from sqlalchemy import delete

    from app.companies.infrastructure.models import RolePermissionModel

    headers = register(api_client, "permissions@example.com")
    company = api_client.post("/companies", json=COMPANY, headers=headers).json()
    _, connection = auth_service
    connection.execute(
        delete(RolePermissionModel).where(
            RolePermissionModel.role_code == "OWNER",
            RolePermissionModel.permission_code == "company.update",
        )
    )
    assert (
        api_client.patch(
            f"/companies/{company['id']}",
            headers=headers,
            json={"company_name": "수정", "expected_version": 1},
        ).status_code
        == 403
    )


def test_password_and_tokens_never_enter_database_or_logs(
    api_client: TestClient, auth_service, caplog
) -> None:
    import logging

    from app.core.security import digest
    from app.identity.sessions.infrastructure.models import RefreshSessionModel

    caplog.set_level(logging.INFO)
    response = api_client.post(
        "/auth/register", json={"email": "secret@example.com", "password": PASSWORD}
    )
    assert response.status_code == 201
    refresh = api_client.cookies.get("aao-refresh")
    access = response.json()["access_token"]
    _, connection = auth_service
    password_hash = connection.scalar(select(UserModel.password_hash))
    token_hash = connection.scalar(select(RefreshSessionModel.refresh_token_hash))
    assert password_hash != PASSWORD and password_hash.startswith("$argon2id$")
    assert token_hash == digest(refresh) and token_hash != refresh
    api_client.post(
        "/invitations/" + "a" * 43 + "/accept", headers={"Authorization": f"Bearer {access}"}
    )
    for secret in (PASSWORD, refresh, access, "a" * 43):
        assert secret not in caplog.text


def test_admin_cannot_invite_owner(api_client: TestClient, auth_service) -> None:
    headers = register(api_client, "admin@example.com")
    company = api_client.post("/companies", json=COMPANY, headers=headers).json()
    _, connection = auth_service
    connection.execute(update(MembershipModel).values(role_code="ADMIN"))
    response = api_client.post(
        f"/companies/{company['id']}/invitations",
        headers=headers,
        json={"email": "invited@example.com", "role_code": "OWNER"},
    )
    assert response.status_code == 403


def test_invitation_cannot_restore_revoked_membership(api_client: TestClient, auth_service) -> None:
    from sqlalchemy import insert

    owner = register(api_client, "owner@example.com")
    company = api_client.post("/companies", json=COMPANY, headers=owner).json()
    member = register(api_client, "revoked@example.com")
    user = api_client.get("/auth/me", headers=member).json()
    _, connection = auth_service
    now = datetime.now(UTC)
    connection.execute(
        insert(MembershipModel).values(
            id=uuid4(),
            company_id=UUID(company["id"]),
            user_id=UUID(user["id"]),
            role_code="VIEWER",
            status="REVOKED",
            joined_at=now,
            revoked_at=now,
            version=1,
        )
    )
    invitation = api_client.post(
        f"/companies/{company['id']}/invitations",
        headers=owner,
        json={"email": "revoked@example.com", "role_code": "VIEWER"},
    )
    assert invitation.status_code == 201
    token = invitation.json()["invite_token"]
    assert api_client.post(f"/invitations/{token}/accept", headers=member).status_code == 403
