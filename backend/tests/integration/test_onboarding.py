"""실제 PostgreSQL과 기존 파일 파서로 초안·충돌·승격을 검증합니다."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update

from app.companies.infrastructure.models import CompanyModel, MembershipModel
from app.intake.infrastructure.parser import XLSX_MIME
from app.onboarding.infrastructure.models import (
    ApplyReceiptModel,
    PromotionReceiptModel,
    ValueHistoryModel,
)
from app.onboarding.infrastructure.template import template_sheets, workbook_bytes


def setup(client):
    response = client.post(
        "/auth/register",
        json={"email": "onboarding@example.com", "password": "StrongPassword!2026"},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    response = client.post(
        "/companies",
        headers=headers,
        json={
            "company_name": "새 회사",
            "business_number": "1234567890",
            "corporation_number": "1234567890123",
            "taxpayer_type": "CORPORATION",
            "opening_date": "2025-01-01",
            "address": "테스트 주소",
        },
    )
    assert response.status_code == 201, response.text
    headers["X-Company-ID"] = response.json()["id"]
    workspace = client.get("/onboarding", headers=headers)
    assert workspace.status_code == 200, workspace.text
    return headers, workspace.json()


def save(client, headers, workspace, values):
    response = client.patch(
        "/onboarding/values",
        headers=headers,
        json={
            "expected_version": workspace["version"],
            "values": [
                {"field_code": code, "row_key": key, "value": value} for code, key, value in values
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def upload(client, headers, *, name="파일 회사", amount=None):
    sheets = template_sheets()
    header = sheets["Company"][0]
    row = {"company_name": name}
    sheets["Company"].append([str(row.get(code, "")) for code in header])
    if amount is not None:
        header = sheets["Opening_Balances"][0]
        row = {
            "as_of_date": "2025-01-01",
            "account_code": "101",
            "debit_amount": amount,
            "credit_amount": "0",
        }
        sheets["Opening_Balances"].append([str(row.get(code, "")) for code in header])
    response = client.post(
        "/onboarding/imports",
        headers=headers,
        files={"file": ("onboarding.xlsx", workbook_bytes(sheets), XLSX_MIME)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, headers, workspace, imported):
    response = client.post(
        f"/onboarding/imports/{imported['import_id']}/preview",
        headers=headers,
        json={"expected_version": workspace["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def apply(client, headers, draft, choices, key="apply-one"):
    return client.post(
        f"/onboarding/imports/{draft['import_id']}/apply",
        headers={**headers, "Idempotency-Key": key},
        json={
            "expected_version": draft["session_version"],
            "preview_digest": draft["digest"],
            "choices": choices,
        },
    )


def ready(client, headers, workspace):
    return save(
        client,
        headers,
        workspace,
        [
            ("Company.no_opening_balance", "singleton", True),
            ("COA.account_code", "101", "101"),
            ("COA.account_name", "101", "현금"),
            ("COA.account_type", "101", "ASSET"),
            ("COA.normal_balance", "101", "DEBIT"),
            ("COA.posting_allowed", "101", True),
        ],
    )


def test_manual_save_resume_version_and_extra_rejection(api_client):
    headers, current = setup(api_client)
    updated = save(
        api_client, headers, current, [("Company.company_name", "singleton", "직접 입력 회사")]
    )
    resumed = api_client.get("/onboarding", headers=headers).json()
    assert resumed == updated
    assert any(
        c["value"] == "직접 입력 회사" and c["source_type"] == "MANUAL" for c in resumed["cells"]
    )
    response = api_client.patch(
        "/onboarding/values",
        headers=headers,
        json={
            "expected_version": current["version"],
            "values": [{"field_code": "Company.company_name", "value": "충돌"}],
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ONBOARDING_IMPORT_STALE"
    response = api_client.post(
        "/onboarding/validate",
        headers=headers,
        json={"expected_version": updated["version"], "extra": 1},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("choice", ["KEEP_CURRENT", "APPLY_IMPORT"])
def test_manual_excel_conflict_apply_replay_and_manual_history(api_client, auth_service, choice):
    headers, current = setup(api_client)
    current = save(
        api_client, headers, current, [("Company.company_name", "singleton", "수동 회사")]
    )
    imported = upload(api_client, headers)
    draft = preview(api_client, headers, current, imported)
    assert draft["counts"]["CONFLICT"] == 1
    response = apply(api_client, headers, draft, {"Company.company_name:singleton": choice})
    assert response.status_code == 200, response.text
    assert (
        apply(api_client, headers, draft, {"Company.company_name:singleton": choice}).json()
        == response.json()
    )
    assert (
        apply(
            api_client,
            headers,
            draft,
            {
                "Company.company_name:singleton": "KEEP_CURRENT"
                if choice == "APPLY_IMPORT"
                else "APPLY_IMPORT"
            },
        ).status_code
        == 409
    )
    workspace = api_client.get("/onboarding", headers=headers).json()
    cell = next(c for c in workspace["cells"] if c["field_code"] == "Company.company_name")
    assert cell["value"] == ("수동 회사" if choice == "KEEP_CURRENT" else "파일 회사")
    workspace = save(
        api_client, headers, workspace, [("Company.company_name", "singleton", "다시 수정")]
    )
    assert (
        next(c for c in workspace["cells"] if c["field_code"] == "Company.company_name")[
            "source_type"
        ]
        == "MANUAL"
    )
    connection = auth_service[1]
    assert connection.scalar(select(func.count()).select_from(ValueHistoryModel)) >= 2
    assert connection.scalar(select(func.count()).select_from(ApplyReceiptModel)) == 1


def test_stale_apply_and_cross_company(api_client):
    headers, current = setup(api_client)
    imported = upload(api_client, headers)
    draft = preview(api_client, headers, current, imported)
    save(api_client, headers, current, [("Company.company_name", "singleton", "수정")])
    assert (
        apply(
            api_client, headers, draft, {"Company.company_name:singleton": "APPLY_IMPORT"}
        ).status_code
        == 409
    )
    foreign = {**headers, "X-Company-ID": str(uuid4())}
    assert (
        api_client.get(f"/onboarding/imports/{imported['import_id']}", headers=foreign).status_code
        == 404
    )


def test_opening_data_stale_recalculation_and_future_promotion_block(api_client):
    headers, current = setup(api_client)
    imported = upload(api_client, headers, amount="123.4500")
    draft = preview(api_client, headers, current, imported)
    response = apply(api_client, headers, draft, {"Company.company_name:singleton": "KEEP_CURRENT"})
    assert response.status_code == 200, response.text
    current = api_client.get("/onboarding", headers=headers).json()
    assert any(c["status"] == "STALE" for c in current["cells"] if c["source_type"] == "DERIVED")
    response = api_client.post(
        "/onboarding/validate", headers=headers, json={"expected_version": current["version"]}
    )
    assert response.status_code == 200, response.text
    assert any(i["validation_code"] == "PENDING_DOMAIN_SUPPORT" for i in response.json()["issues"])
    assert (
        next(
            c
            for c in response.json()["workspace"]["cells"]
            if c["field_code"].endswith("debit_total")
        )["value"]
        == "123.4500"
    )
    assert (
        api_client.post(
            "/onboarding/complete",
            headers={**headers, "Idempotency-Key": "complete"},
            json={"expected_version": response.json()["workspace"]["version"]},
        ).status_code
        == 409
    )


def test_complete_atomic_and_idempotent(api_client, auth_service):
    headers, current = setup(api_client)
    current = ready(api_client, headers, current)
    response = api_client.post(
        "/onboarding/validate", headers=headers, json={"expected_version": current["version"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["issues"] == []
    current = response.json()["workspace"]
    request = {"expected_version": current["version"]}
    response = api_client.post(
        "/onboarding/complete", headers={**headers, "Idempotency-Key": "complete"}, json=request
    )
    assert response.status_code == 200, response.text
    assert (
        api_client.post(
            "/onboarding/complete", headers={**headers, "Idempotency-Key": "complete"}, json=request
        ).json()
        == response.json()
    )
    assert auth_service[1].scalar(select(func.count()).select_from(PromotionReceiptModel)) == 1


def test_complete_rolls_back_company_change(api_client, auth_service, monkeypatch):
    from app.onboarding.application import complete

    headers, current = setup(api_client)
    current = ready(api_client, headers, current)
    current = save(
        api_client, headers, current, [("Company.company_name", "singleton", "승격 실패 회사")]
    )

    def fail(*args, **kwargs):
        raise RuntimeError("테스트 중간 실패")

    monkeypatch.setattr(complete, "promote_accounting", fail)
    response = api_client.post(
        "/onboarding/complete",
        headers={**headers, "Idempotency-Key": "fail"},
        json={"expected_version": current["version"]},
    )
    assert response.status_code == 500
    assert (
        auth_service[1].scalar(
            select(CompanyModel.company_name).where(
                CompanyModel.id == UUID(headers["X-Company-ID"])
            )
        )
        == "새 회사"
    )
    assert auth_service[1].scalar(select(func.count()).select_from(PromotionReceiptModel)) == 0


def test_revoked_membership_and_viewer_denied(api_client, auth_service):
    headers, current = setup(api_client)
    connection = auth_service[1]
    connection.execute(
        update(MembershipModel)
        .where(MembershipModel.company_id == UUID(headers["X-Company-ID"]))
        .values(role_code="VIEWER")
    )
    assert api_client.get("/onboarding", headers=headers).status_code == 200
    assert (
        api_client.post(
            "/onboarding/validate", headers=headers, json={"expected_version": current["version"]}
        ).status_code
        == 403
    )
    connection.execute(
        update(MembershipModel)
        .where(MembershipModel.company_id == UUID(headers["X-Company-ID"]))
        .values(status="REVOKED", revoked_at=datetime.now(UTC))
    )
    assert api_client.get("/onboarding", headers=headers).status_code == 404


def test_mapped_counterparty_file_reuses_intake_and_freezes_after_apply(api_client, auth_service):
    headers, current = setup(api_client)
    auth_service[1].execute(
        update(MembershipModel)
        .where(MembershipModel.company_id == UUID(headers["X-Company-ID"]))
        .values(role_code="ACCOUNTANT")
    )
    response = api_client.post(
        "/imports",
        headers=headers,
        data={"source_type": "COUNTERPARTY", "target_context": "ONBOARDING_DRAFT"},
        files={
            "file": (
                "counterparties.csv",
                b"source_id,display_name,role_code\nC001,Customer,CUSTOMER\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 201, response.text
    imported = response.json()
    response = api_client.post(
        "/onboarding/imports", headers=headers, json={"existing_import_id": imported["id"]}
    )
    assert response.status_code == 201, response.text
    draft = preview(api_client, headers, current, response.json())
    assert not draft["errors"]
    assert any(
        item["incoming"]["field_code"] == "Counterparties.role_code" for item in draft["items"]
    )
    blocked = api_client.post(
        f"/imports/{imported['id']}/confirm",
        headers={**headers, "Idempotency-Key": "generic-bypass"},
        json={
            "expected_version": imported["version"],
            "preview_digest": draft["digest"],
            "confirmed": True,
        },
    )
    assert blocked.status_code == 409
    response = apply(api_client, headers, draft, {})
    assert response.status_code == 200, response.text
    assert (
        api_client.get(f"/imports/{imported['id']}", headers=headers).json()["status"]
        == "COMPLETED"
    )
    restored = api_client.get("/onboarding", headers=headers).json()
    assert any(
        c["field_code"] == "Counterparties.counterparty_code" and c["value"] == "C001"
        for c in restored["cells"]
    )


def test_onboarding_rejects_macro_extension_and_float_values(api_client):
    headers, current = setup(api_client)
    response = api_client.post(
        "/onboarding/imports",
        headers=headers,
        files={"file": ("template.xlsm", workbook_bytes(template_sheets()), XLSX_MIME)},
    )
    assert response.status_code == 422
    response = api_client.patch(
        "/onboarding/values",
        headers=headers,
        json={
            "expected_version": current["version"],
            "values": [
                {
                    "field_code": "Opening_Balances.debit_amount",
                    "row_key": "2025-01-01|101|",
                    "value": 0.1,
                }
            ],
        },
    )
    assert response.status_code == 422


def test_real_company_switch_and_same_company_requester_isolation(api_client, auth_service):
    headers, current = setup(api_client)
    imported = upload(api_client, headers)
    response = api_client.post(
        "/companies",
        headers=headers,
        json={
            "company_name": "두 번째 회사",
            "business_number": "9876543210",
            "taxpayer_type": "INDIVIDUAL",
            "opening_date": "2025-01-01",
            "address": "합성 주소",
        },
    )
    assert response.status_code == 201, response.text
    foreign = {**headers, "X-Company-ID": response.json()["id"]}
    assert (
        api_client.get(f"/onboarding/imports/{imported['import_id']}", headers=foreign).status_code
        == 404
    )
    response = api_client.get("/onboarding", headers=foreign)
    assert response.status_code == 200
    assert response.json()["id"] != current["id"]
    other = api_client.post(
        "/auth/register",
        json={"email": "other-onboarding@example.com", "password": "StrongPassword!2026"},
    ).json()
    auth_service[1].execute(
        MembershipModel.__table__.insert().values(
            id=uuid4(),
            company_id=UUID(headers["X-Company-ID"]),
            user_id=UUID(other["user"]["id"]),
            role_code="OWNER",
        )
    )
    shared = {
        "Authorization": "Bearer " + other["access_token"],
        "X-Company-ID": headers["X-Company-ID"],
    }
    assert api_client.get("/onboarding", headers=shared).status_code == 200
    assert (
        api_client.get(f"/onboarding/imports/{imported['import_id']}", headers=shared).status_code
        == 403
    )
