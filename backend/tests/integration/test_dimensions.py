"""관리차원은 회사 경계와 확정 전표 불변식을 유지하며 원장 조회만 좁힙니다."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.test_journal_flow import command, prepare


def create_dimension(client, headers, code="DEPT", kind="DEPARTMENT", **extra):
    response = client.post(
        "/accounting/dimensions",
        headers=headers,
        json={
            "dimension_code": code,
            "name": "관리 부서",
            "dimension_type": kind,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_value(client, headers, dimension, code="SALES", **extra):
    response = client.post(
        f"/accounting/dimensions/{dimension['id']}/values",
        headers=headers,
        json={"value_code": code, "name": "영업팀", **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_dimension_journal_post_and_filtered_ledger(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    dimension = create_dimension(api_client, writer)
    value = create_value(api_client, writer, dimension)
    payload["lines"][0]["dimension_value_ids"] = [value["id"]]
    response = api_client.post(
        "/journals", headers={**writer, "Idempotency-Key": str(uuid4())}, json=payload
    )
    assert response.status_code == 201, response.text
    journal = response.json()
    assert journal["lines"][0]["dimension_value_ids"] == [value["id"]]
    for actor, action in (
        (writer, "submit"),
        (writer, "request-review"),
        (owner, "approve"),
        (owner, "post"),
    ):
        response = command(api_client, actor, journal, action)
        assert response.status_code == 200, response.text
        journal = response.json()
    params = {
        "account_id": payload["lines"][0]["account_id"],
        "date_from": "2026-01-01",
        "date_to": "2026-01-31",
    }
    plain = api_client.get("/ledger", headers=writer, params=params).json()
    filtered = api_client.get(
        "/ledger", headers=writer, params={**params, "dimension_value_id": value["id"]}
    ).json()
    assert plain == filtered and filtered[0]["running_balance"] == "100.0000"
    trial = api_client.get(
        "/trial-balance", headers=writer, params={"period_id": payload["accounting_period_id"]}
    ).json()
    assert sum(Decimal(r["period_debit"]) for r in trial) == 100
    with pytest.raises(IntegrityError) as blocked:
        with connection.begin_nested():
            connection.execute(
                text("DELETE FROM journal_line_dimensions WHERE journal_line_id=:id"),
                {"id": journal["lines"][0]["id"]},
            )
    assert blocked.value.orig.sqlstate == "23514"
    with pytest.raises(IntegrityError) as blocked:
        with connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE journal_line_dimensions SET dimension_value_id=dimension_value_id "
                    "WHERE journal_line_id=:id"
                ),
                {"id": journal["lines"][0]["id"]},
            )
    assert blocked.value.orig.sqlstate == "23514"
    with pytest.raises(IntegrityError) as blocked:
        with connection.begin_nested():
            connection.execute(
                text(
                    "INSERT INTO journal_line_dimensions "
                    "(id,company_id,journal_line_id,dimension_id,"
                    "dimension_type,dimension_value_id) "
                    "SELECT :new_id, company_id, journal_line_id, dimension_id, dimension_type, "
                    "dimension_value_id FROM journal_line_dimensions WHERE journal_line_id=:id"
                ),
                {"id": journal["lines"][0]["id"], "new_id": uuid4()},
            )
    assert blocked.value.orig.sqlstate == "23514"


def test_dimension_version_hierarchy_and_company_scope(api_client, auth_service):
    _, writer, _, _ = prepare(api_client, auth_service)
    dimension = create_dimension(api_client, writer)
    value = create_value(api_client, writer, dimension)
    path = f"/accounting/dimensions/{dimension['id']}"
    update = {
        "expected_version": 1,
        "name": "관리부서",
        "status": "ACTIVE",
        "required_policy": "OPTIONAL",
    }
    assert api_client.patch(path, headers=writer, json=update).status_code == 200
    assert api_client.patch(path, headers=writer, json=update).status_code == 409
    another = create_dimension(api_client, writer, "PROJECT", "PROJECT")
    response = api_client.post(
        f"/accounting/dimensions/{another['id']}/values",
        headers=writer,
        json={"value_code": "X", "name": "잘못된 상위", "parent_value_id": value["id"]},
    )
    assert response.status_code == 404
    response = api_client.patch(
        path + f"/values/{value['id']}",
        headers=writer,
        json={
            "expected_version": 1,
            "value_code": "SALES",
            "name": "순환",
            "parent_value_id": value["id"],
        },
    )
    assert response.status_code == 422
    assert (
        api_client.get(
            path + "/values", headers={**writer, "X-Company-ID": str(uuid4())}
        ).status_code
        == 404
    )
    assert (
        api_client.post(
            "/accounting/dimensions",
            json={"dimension_code": "NO", "name": "거부", "dimension_type": "PROJECT"},
        ).status_code
        == 401
    )


def test_post_rechecks_inactive_dimension_value(api_client, auth_service):
    owner, writer, payload, _ = prepare(api_client, auth_service)
    dimension = create_dimension(api_client, writer)
    value = create_value(api_client, writer, dimension)
    payload["lines"][0]["dimension_value_ids"] = [value["id"]]
    journal = api_client.post(
        "/journals", headers={**writer, "Idempotency-Key": str(uuid4())}, json=payload
    ).json()
    for actor, action in ((writer, "submit"), (writer, "request-review"), (owner, "approve")):
        response = command(api_client, actor, journal, action)
        assert response.status_code == 200, response.text
        journal = response.json()
    response = api_client.patch(
        f"/accounting/dimensions/{dimension['id']}/values/{value['id']}",
        headers=writer,
        json={"expected_version": 1, "value_code": "SALES", "name": "영업팀", "status": "INACTIVE"},
    )
    assert response.status_code == 200, response.text
    response = command(api_client, owner, journal, "post")
    assert response.status_code == 422 and response.json()["code"] == "DIMENSION_VALUE_INVALID"


def test_dimension_permission_and_input_contract(api_client, auth_service):
    _, writer, payload, connection = prepare(api_client, auth_service)
    dimension = create_dimension(api_client, writer)
    future = create_value(api_client, writer, dimension, effective_from="2027-01-01")
    payload["lines"][0]["dimension_value_ids"] = [future["id"]]
    response = api_client.post(
        "/journals", headers={**writer, "Idempotency-Key": str(uuid4())}, json=payload
    )
    assert response.status_code == 422
    assert response.json()["code"] == "DIMENSION_VALUE_INVALID"
    invalid = api_client.post(
        "/accounting/dimensions",
        headers=writer,
        json={
            "dimension_code": "X",
            "name": "부서",
            "dimension_type": "PROJECT",
            "company_id": str(uuid4()),
        },
    )
    assert invalid.status_code == 422
    connection.execute(
        text(
            "UPDATE company_memberships SET role_code='VIEWER' "
            "WHERE company_id=:company AND role_code='ACCOUNTANT'"
        ),
        {"company": writer["X-Company-ID"]},
    )
    assert api_client.get("/accounting/dimensions", headers=writer).status_code == 200
    denied = api_client.post(
        f"/accounting/dimensions/{dimension['id']}/values",
        headers=writer,
        json={"value_code": "DENIED", "name": "읽기 전용"},
    )
    assert denied.status_code == 403


def test_cross_company_values_and_csrf(api_client, auth_service):
    owner, writer, payload, _ = prepare(api_client, auth_service)
    dimension = create_dimension(api_client, writer)
    value = create_value(api_client, writer, dimension)
    response = api_client.post(
        "/companies",
        headers=owner,
        json={
            "company_name": "분리된 회사",
            "taxpayer_type": "CORPORATION",
            "business_number": "9876543210",
            "opening_date": "2026-01-01",
            "address": "검증 주소",
        },
    )
    assert response.status_code == 201, response.text
    foreign = {**owner, "X-Company-ID": response.json()["id"]}
    other = create_dimension(api_client, foreign)
    other_value = create_value(api_client, foreign, other)
    assert (
        api_client.get(
            f"/accounting/dimensions/{dimension['id']}/values", headers=foreign
        ).status_code
        == 404
    )
    response = api_client.post(
        f"/accounting/dimensions/{dimension['id']}/values",
        headers=writer,
        json={
            "value_code": "BAD_PARENT",
            "name": "다른 회사 상위항목",
            "parent_value_id": other_value["id"],
        },
    )
    assert response.status_code == 404

    payload["lines"][0]["dimension_value_ids"] = [other_value["id"]]
    response = api_client.post(
        "/journals", headers={**writer, "Idempotency-Key": str(uuid4())}, json=payload
    )
    assert response.status_code == 422
    assert response.json()["code"] == "DIMENSION_VALUE_INVALID"
    response = api_client.post(
        f"/accounting/dimensions/{dimension['id']}/values",
        headers={**writer, "X-CSRF-Protection": "0"},
        json={"value_code": "NO_CSRF", "name": "거부"},
    )
    assert response.status_code == 403
    response = api_client.get(
        "/ledger",
        headers=foreign,
        params={
            "account_id": payload["lines"][0]["account_id"],
            "dimension_value_id": value["id"],
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        },
    )
    assert response.status_code == 404


def test_required_dimension_policy_and_draft_compatibility(api_client, auth_service):
    _, writer, payload, _ = prepare(api_client, auth_service)
    create_dimension(api_client, writer, required_policy="REQUIRED")
    duplicate = api_client.post(
        "/accounting/dimensions",
        headers=writer,
        json={
            "dimension_code": "OTHER",
            "name": "중복 필수 부서",
            "dimension_type": "DEPARTMENT",
            "required_policy": "REQUIRED",
        },
    )
    assert duplicate.status_code == 422
    assert duplicate.json()["code"] == "DIMENSION_DUPLICATE_TYPE"
    draft = api_client.post(
        "/journals", headers={**writer, "Idempotency-Key": str(uuid4())}, json=payload
    )
    assert draft.status_code == 201
    submitted = command(api_client, writer, draft.json(), "submit")
    assert submitted.status_code == 422
    assert submitted.json()["code"] == "DIMENSION_VALUE_INVALID"
