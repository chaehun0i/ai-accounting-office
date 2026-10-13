"""월마감의 실제 PostgreSQL 기간 잠금과 두 사람 승인을 검증합니다."""

from calendar import monthrange
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounting.periods.infrastructure.models import PeriodModel
from app.closing.infrastructure.models import ClosingCheckModel
from app.companies.infrastructure.models import MembershipModel
from tests.fixtures.reconciliation.adapter import canonical_csv
from tests.integration.test_bank_reconciliation import prepare_bank
from tests.integration.test_journal_flow import command, prepare


def request(client, headers, path, payload=None, key=None):
    return client.post(
        path,
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
        json=payload or {},
    )


def reviewer(client, owner, connection):
    response = client.post(
        "/auth/register",
        json={"email": "reviewer-closing@example.com", "password": "StrongPassword!2026"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    user = client.get("/auth/me", headers={"Authorization": "Bearer " + token}).json()
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        session.add(
            MembershipModel(
                id=uuid4(),
                company_id=UUID(owner["X-Company-ID"]),
                user_id=UUID(user["id"]),
                role_code="REVIEWER",
                status="ACTIVE",
                joined_at=datetime.now(UTC),
                version=1,
            )
        )
        session.commit()
    return {**owner, "Authorization": "Bearer " + token}


def test_close_requires_fresh_checks_and_separate_reviewer(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    period_id = payload["accounting_period_id"]
    key = "closing-start-1"
    started = request(api_client, writer, "/closing-runs", {"accounting_period_id": period_id}, key)
    assert started.status_code == 201, started.text
    run = started.json()
    assert run["status"] == "ACTIVE"
    assert (
        request(
            api_client, writer, "/closing-runs", {"accounting_period_id": period_id}, key
        ).json()["id"]
        == run["id"]
    )
    assert api_client.get("/closing/periods", headers=owner).json()[0]["status"] == "CLOSING"
    detail = api_client.get(f"/closing-runs/{run['id']}", headers=owner).json()
    assert all(check["severity"] == "PASS" for check in detail["checks"]), detail
    assert (
        request(
            api_client, writer, f"/closing-runs/{run['id']}/close", {"approval_id": str(uuid4())}
        ).status_code
        == 403
    )
    submitted = request(
        api_client, review, f"/closing-runs/{run['id']}/submit", {"reason": "월말 검토"}
    )
    assert submitted.status_code == 200, submitted.text
    approval = submitted.json()
    assert (
        request(
            api_client, review, f"/closing-approvals/{approval['id']}/approve", {"reason": "승인"}
        ).status_code
        == 403
    )
    approved = request(
        api_client, owner, f"/closing-approvals/{approval['id']}/approve", {"reason": "검사 완료"}
    )
    assert approved.status_code == 200, approved.text
    closed = request(
        api_client,
        owner,
        f"/closing-runs/{run['id']}/close",
        {"approval_id": approval["id"]},
        key="closing-finish-1",
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "COMPLETED"
    assert (
        request(
            api_client,
            owner,
            f"/closing-runs/{run['id']}/close",
            {"approval_id": approval["id"]},
            key="closing-finish-1",
        ).status_code
        == 200
    )
    period = api_client.get("/closing/periods", headers=owner).json()[0]
    assert period["status"] == "CLOSED" and period["close_version"] == 1
    assert len(api_client.get(f"/closing/periods/{period_id}/runs", headers=owner).json()) == 1
    assert api_client.get(
        f"/closing-runs/{run['id']}", headers={**owner, "X-Company-ID": str(uuid4())}
    ).status_code in {403, 404}


def test_unapproved_journal_blocks_close_and_closing_blocks_general_posting(
    api_client, auth_service
):
    owner, writer, payload, _ = prepare(api_client, auth_service)
    journal = request(api_client, writer, "/journals", payload)
    assert journal.status_code == 201, journal.text
    started = request(
        api_client,
        writer,
        "/closing-runs",
        {"accounting_period_id": payload["accounting_period_id"]},
    )
    assert started.status_code == 201, started.text
    run = started.json()
    checks = api_client.get(f"/closing-runs/{run['id']}", headers=writer).json()["checks"]
    assert any(c["check_code"] == "JOURNALS_PENDING" and c["severity"] == "BLOCKER" for c in checks)
    assert (
        request(
            api_client, owner, f"/closing-runs/{run['id']}/submit", {"reason": "차단"}
        ).status_code
        == 409
    )
    assert request(api_client, writer, "/journals", payload).status_code == 409


def test_adjustment_uses_existing_journal_review_and_posting(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    run = request(
        api_client,
        writer,
        "/closing-runs",
        {"accounting_period_id": payload["accounting_period_id"]},
    ).json()
    created = request(
        api_client,
        writer,
        f"/closing-runs/{run['id']}/adjustments",
        {
            "adjustment_type": "ACCRUED_EXPENSE",
            "entry_date": payload["entry_date"],
            "description": "결산 발생비용",
            "lines": payload["lines"],
            "auto_reverse": True,
            "scheduled_reversal_date": "2026-02-01",
        },
    )
    assert created.status_code == 201, created.text
    adjustment = created.json()
    journal = api_client.get(
        f"/journals/{adjustment['proposed_journal_id']}", headers=writer
    ).json()
    assert journal["source_type"] == "CLOSING" and journal["status"] == "DRAFT"
    assert (
        request(
            api_client, review, f"/closing-runs/{run['id']}/submit", {"reason": "조정 전"}
        ).status_code
        == 409
    )
    for actor, action in [
        (writer, "submit"),
        (writer, "request-review"),
        (owner, "approve"),
        (owner, "post"),
    ]:
        response = command(api_client, actor, journal, action)
        assert response.status_code == 200, response.text
        journal = response.json()
    assert journal["status"] == "POSTED"
    rerun = request(api_client, writer, f"/closing-runs/{run['id']}/checks")
    assert rerun.status_code == 200, rerun.text
    checks = rerun.json()["checks"]
    assert all(c["severity"] == "PASS" for c in checks), checks
    assert rerun.json()["adjustments"][0]["status"] == "POSTED"
    approval = request(
        api_client, review, f"/closing-runs/{run['id']}/submit", {"reason": "조정 검토"}
    )
    assert approval.status_code == 200, approval.text
    approved = request(
        api_client, owner, f"/closing-approvals/{approval.json()['id']}/approve", {"reason": "확인"}
    )
    assert approved.status_code == 200, approved.text
    closed = request(
        api_client,
        owner,
        f"/closing-runs/{run['id']}/close",
        {"approval_id": approval.json()["id"]},
    )
    assert closed.status_code == 200, closed.text
    tb = api_client.get(f"/closing-runs/{run['id']}/trial-balance?stage=ADJUSTED", headers=owner)
    assert tb.status_code == 200 and len(tb.json()["rows"]) == 2
    reversal = request(
        api_client,
        owner,
        f"/closing-adjustments/{adjustment['id']}/reversal",
        {"reason": "다음 기간 자동 역분개 초안"},
        key="reversal-1",
    )
    assert reversal.status_code == 201, reversal.text
    assert reversal.json()["status"] == "DRAFT"
    assert reversal.json()["reversal_of_id"] == journal["id"]
    assert (
        request(
            api_client,
            owner,
            f"/closing-adjustments/{adjustment['id']}/reversal",
            {"reason": "다음 기간 자동 역분개 초안"},
            key="reversal-1",
        ).json()["id"]
        == reversal.json()["id"]
    )


def test_stale_run_and_reopen_history(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    period_id = payload["accounting_period_id"]
    run = request(api_client, writer, "/closing-runs", {"accounting_period_id": period_id}).json()
    approval = request(
        api_client, review, f"/closing-runs/{run['id']}/submit", {"reason": "마감"}
    ).json()
    request(api_client, owner, f"/closing-approvals/{approval['id']}/approve", {"reason": "확인"})
    closed = request(
        api_client, owner, f"/closing-runs/{run['id']}/close", {"approval_id": approval["id"]}
    )
    assert closed.status_code == 200, closed.text
    reopen_request = request(
        api_client, writer, f"/closing-runs/{run['id']}/reopen-request", {"reason": "정정 필요"}
    )
    assert reopen_request.status_code == 200, reopen_request.text
    reopened_approval = request(
        api_client,
        owner,
        f"/closing-approvals/{reopen_request.json()['id']}/approve",
        {"reason": "재개 승인"},
    )
    assert reopened_approval.status_code == 200, reopened_approval.text
    opened = request(
        api_client,
        owner,
        f"/closing-runs/{run['id']}/reopen",
        {"approval_id": reopen_request.json()["id"], "reason": "정정"},
    )
    assert opened.status_code == 200 and opened.json()["close_version"] == 2
    next_run = request(api_client, writer, "/closing-runs", {"accounting_period_id": period_id})
    assert next_run.status_code == 201 and next_run.json()["run_version"] == 2
    assert len(api_client.get(f"/closing/periods/{period_id}/runs", headers=owner).json()) == 2


def test_new_transaction_stales_run_and_check_history_is_append_only(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    period_id = payload["accounting_period_id"]
    run = request(api_client, writer, "/closing-runs", {"accounting_period_id": period_id}).json()
    transaction = request(
        api_client,
        writer,
        "/transactions",
        {
            "transaction_date": payload["entry_date"],
            "accounting_date": payload["entry_date"],
            "description": "마감 검사 후 도착한 거래",
            "amount": "100.0000",
            "direction": "INFLOW",
            "source_id": "closing-stale-transaction",
        },
    )
    assert transaction.status_code == 201, transaction.text
    stale = request(api_client, owner, f"/closing-runs/{run['id']}/submit", {"reason": "기존 검사"})
    assert stale.status_code == 409 and stale.json()["code"] == "CLOSING_RUN_STALE"
    rerun = request(api_client, writer, f"/closing-runs/{run['id']}/checks")
    assert rerun.status_code == 200
    assert any(
        check["check_code"] == "TRANSACTIONS_PENDING" and check["severity"] == "BLOCKER"
        for check in rerun.json()["checks"]
    )
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        count = session.scalar(
            select(func.count())
            .select_from(ClosingCheckModel)
            .where(
                ClosingCheckModel.company_id == UUID(owner["X-Company-ID"]),
                ClosingCheckModel.closing_run_id == UUID(run["id"]),
            )
        )
    assert count == 16


def test_service_bank_source_blocks_month_close_until_reconciled(api_client, auth_service):
    owner, writer, payload = prepare_bank(
        api_client, auth_service, canonical_csv("service", "Bank"), "200000"
    )
    imported = request(api_client, writer, "/bank-statements/imports", payload)
    assert imported.status_code == 200, imported.text
    period = api_client.get("/accounting/periods", headers=owner).json()[0]
    run = request(api_client, writer, "/closing-runs", {"accounting_period_id": period["id"]})
    assert run.status_code == 201, run.text
    checks = api_client.get(f"/closing-runs/{run.json()['id']}", headers=owner).json()["checks"]
    assert any(
        check["check_code"] == "BANK_CARD_UNRECONCILED" and check["severity"] == "BLOCKER"
        for check in checks
    )


def test_2025_monthly_close_history_preserves_each_run(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    company = UUID(owner["X-Company-ID"])
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        for month in range(1, 13):
            session.add(
                PeriodModel(
                    id=uuid4(),
                    company_id=company,
                    fiscal_year=2025,
                    period_no=month,
                    start_date=date(2025, month, 1),
                    end_date=date(2025, month, monthrange(2025, month)[1]),
                    status="OPEN",
                    version=1,
                )
            )
        session.commit()
    periods = [
        period
        for period in api_client.get("/accounting/periods", headers=owner).json()
        if period["start_date"].startswith("2025-")
    ]
    assert len(periods) == 12
    for period in periods:
        run = request(api_client, writer, "/closing-runs", {"accounting_period_id": period["id"]})
        assert run.status_code == 201, run.text
        approval = request(
            api_client, review, f"/closing-runs/{run.json()['id']}/submit", {"reason": "월마감"}
        )
        assert approval.status_code == 200, approval.text
        approved = request(
            api_client,
            owner,
            f"/closing-approvals/{approval.json()['id']}/approve",
            {"reason": "독립 검토"},
        )
        assert approved.status_code == 200, approved.text
        closed = request(
            api_client,
            owner,
            f"/closing-runs/{run.json()['id']}/close",
            {"approval_id": approval.json()["id"]},
        )
        assert closed.status_code == 200, closed.text
        assert closed.json()["adjusted_tb_digest"]
    latest = api_client.get("/closing/periods", headers=owner).json()
    assert all(
        p["status"] == "CLOSED" and p["close_version"] == 1
        for p in latest
        if p["start_date"].startswith("2025-")
    )
