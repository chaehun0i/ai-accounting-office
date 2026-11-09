"""PostgreSQL CLOSED BS/IS comparison through independent approval and export."""

from uuid import uuid4

from tests.integration.test_closing_workflow import request, reviewer
from tests.integration.test_finance_flow import post_journal
from tests.integration.test_journal_flow import prepare


def _close(client, owner, writer, review, period_id):
    run = request(client, writer, "/closing-runs", {"accounting_period_id": period_id})
    assert run.status_code == 201, run.text
    approval = request(
        client, review, f"/closing-runs/{run.json()['id']}/submit", {"reason": "마감"}
    )
    assert approval.status_code == 200, approval.text
    approved = request(
        client,
        owner,
        f"/closing-approvals/{approval.json()['id']}/approve",
        {"reason": "마감 확인"},
    )
    assert approved.status_code == 200, approved.text
    closed = request(
        client,
        owner,
        f"/closing-runs/{run.json()['id']}/close",
        {"approval_id": approval.json()["id"]},
    )
    assert closed.status_code == 200, closed.text


def _post_income(client, owner, writer, period_id, date, amount):
    accounts = {
        row["account_name"]: row["id"] for row in client.get("/accounts", headers=writer).json()
    }
    return post_journal(
        client,
        owner,
        writer,
        {"accounting_period_id": period_id, "entry_date": date, "source_type": "MANUAL"},
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": amount},
            {"account_id": accounts["매출"], "credit_amount": amount},
        ],
    )


def test_closed_comparison_reclass_approval_and_report_export(
    api_client, auth_service, monkeypatch
):
    from app.main import RequestIdMiddleware

    async def propagate_exception(self, scope, receive, send):
        await self.app(scope, receive, send)

    monkeypatch.setattr(RequestIdMiddleware, "__call__", propagate_exception)
    owner, writer, _, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    periods = api_client.get("/closing/periods", headers=writer).json()
    prior = next(row for row in periods if row["period_no"] == 1)
    intervening = next(row for row in periods if row["period_no"] == 2)
    current = next(row for row in periods if row["period_no"] == 3)
    _post_income(api_client, owner, writer, prior["id"], "2026-01-02", "100.0000")
    _post_income(api_client, owner, writer, current["id"], "2026-03-02", "125.2500")
    _close(api_client, owner, writer, review, prior["id"])
    _close(api_client, owner, writer, review, intervening["id"])
    _close(api_client, owner, writer, review, current["id"])
    for period in (prior, current):
        generated = api_client.post(
            "/financial-statements/generate",
            headers={**writer, "Idempotency-Key": str(uuid4())},
            json={"period_id": period["id"]},
        )
        assert generated.status_code == 201, generated.text

    query = {"period_id": current["id"], "comparison_period_id": prior["id"]}
    readiness = api_client.get(
        "/financial-statements/comparatives/readiness", headers=writer, params=query
    )
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["status"] == "READY"
    blocked = api_client.get(
        "/financial-statements/comparatives/readiness",
        headers=writer,
        params={"period_id": prior["id"], "comparison_period_id": current["id"]},
    )
    assert blocked.status_code == 200 and blocked.json()["status"] == "BLOCKED"
    headers = {**owner, "Idempotency-Key": str(uuid4())}
    created = api_client.post("/financial-statements/comparatives", headers=headers, json=query)
    assert created.status_code == 201, created.text
    snapshot = created.json()
    replay = api_client.post(
        "/financial-statements/comparatives",
        headers=headers,
        json=query,
    )
    assert replay.status_code == 201 and replay.json()["id"] == snapshot["id"]
    detail = api_client.get(f"/financial-statements/comparatives/{snapshot['id']}", headers=writer)
    assert detail.status_code == 200, detail.text
    revenue = next(
        row
        for row in detail.json()["statements"]["INCOME_STATEMENT"]
        if row["line_code"] == "REVENUE"
    )
    assert revenue["current_amount"] == "125.2500"
    assert revenue["prior_amount"] == "100.0000"

    moved = api_client.post(
        f"/financial-statements/comparatives/{snapshot['id']}/reclassifications",
        headers=owner,
        json={
            "statement_type": "INCOME_STATEMENT",
            "from_line_code": "REVENUE",
            "to_line_code": "NON_OPERATING_INCOME",
            "amount": "25.0000",
            "reason": "표시 분류를 정정한 승인 근거",
            "expected_version": snapshot["version"],
        },
    )
    assert moved.status_code == 200, moved.text
    stale_version = api_client.post(
        f"/financial-statements/comparatives/{snapshot['id']}/reclassifications",
        headers=writer,
        json={
            "statement_type": "INCOME_STATEMENT",
            "from_line_code": "REVENUE",
            "to_line_code": "NON_OPERATING_INCOME",
            "amount": "10.0000",
            "reason": "오래된 버전 요청",
            "expected_version": snapshot["version"],
        },
    )
    assert stale_version.status_code == 409
    revised = api_client.get(
        f"/financial-statements/comparatives/{snapshot['id']}", headers=writer
    ).json()
    revised_lines = {row["line_code"]: row for row in revised["statements"]["INCOME_STATEMENT"]}
    assert revised_lines["REVENUE"]["presentation_amount"] == "75.0000"
    assert revised_lines["NON_OPERATING_INCOME"]["presentation_amount"] == "25.0000"
    assert revised_lines["NET_PROFIT"]["presentation_amount"] == "100.0000"
    own_approval = api_client.post(
        f"/financial-statements/comparatives/{snapshot['id']}/request-review",
        headers=owner,
        json={"expected_version": moved.json()["version"]},
    )
    assert own_approval.status_code == 200, own_approval.text
    self_approve = api_client.post(
        f"/financial-statements/comparatives/{snapshot['id']}/approve",
        headers=owner,
        json={"expected_version": own_approval.json()["version"]},
    )
    assert self_approve.status_code == 409
    approved = api_client.post(
        f"/financial-statements/comparatives/{snapshot['id']}/approve",
        headers=review,
        json={"expected_version": own_approval.json()["version"]},
    )
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    immutable = api_client.post(
        f"/financial-statements/comparatives/{snapshot['id']}/reclassifications",
        headers=writer,
        json={
            "statement_type": "INCOME_STATEMENT",
            "from_line_code": "REVENUE",
            "to_line_code": "NON_OPERATING_INCOME",
            "amount": "1.0000",
            "reason": "승인 후 변경 시도",
            "expected_version": approved.json()["version"],
        },
    )
    assert immutable.status_code == 409

    exported = api_client.post(
        "/reports/generations",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={
            "report_code": "COMPARATIVE_FINANCIAL_STATEMENTS",
            "format": "CSV",
            "period_id": current["id"],
            "comparison_period_id": prior["id"],
            "period_preset": "CUSTOM",
            "date_from": current["start_date"],
            "date_to": current["end_date"],
        },
    )
    assert exported.status_code == 201, exported.text
    run = exported.json()
    assert run["status"] == "COMPLETED"
    file = api_client.get(f"/reports/generations/{run['id']}/download", headers=writer)
    assert file.status_code == 200 and b"prior_presented" in file.content
    assert b"75.0000" in file.content and b"25.0000" in file.content
