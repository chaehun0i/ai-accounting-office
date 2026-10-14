"""마감 후 BS/IS 스냅샷·멱등·드릴다운의 PostgreSQL 폐쇄 루프."""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.closing.infrastructure.models import ClosingRunModel
from app.reporting.financial_statements.infrastructure.models import (
    ReportAccountMappingModel,
    StatementSetModel,
)
from tests.integration.test_closing_workflow import request, reviewer
from tests.integration.test_finance_flow import post_journal
from tests.integration.test_journal_flow import prepare


def closed_company(client, auth_service, *, custom_account=False):
    owner, writer, payload, connection = prepare(client, auth_service)
    review = reviewer(client, owner, connection)
    accounts = {
        row["account_name"]: row["id"] for row in client.get("/accounts", headers=writer).json()
    }
    cash_account = accounts["현금및현금성자산"]
    if custom_account:
        created = client.post(
            "/accounts",
            headers=writer,
            json={
                "account_code": "TEST_CUSTOM_ASSET",
                "account_name": "신규 관리 자산",
                "account_type": "ASSET",
            },
        )
        assert created.status_code == 201, created.text
        cash_account = created.json()["id"]
    journal = post_journal(
        client,
        owner,
        writer,
        {
            "accounting_period_id": payload["accounting_period_id"],
            "entry_date": payload["entry_date"],
            "source_type": "MANUAL",
        },
        [
            {"account_id": cash_account, "debit_amount": "100.0000"},
            {"account_id": accounts["매출"], "credit_amount": "100.0000"},
        ],
    )
    run = request(
        client, writer, "/closing-runs", {"accounting_period_id": payload["accounting_period_id"]}
    )
    assert run.status_code == 201, run.text
    approval = request(
        client, review, f"/closing-runs/{run.json()['id']}/submit", {"reason": "월마감"}
    )
    assert approval.status_code == 200, approval.text
    assert (
        request(
            client, owner, f"/closing-approvals/{approval.json()['id']}/approve", {"reason": "확인"}
        ).status_code
        == 200
    )
    closed = request(
        client,
        owner,
        f"/closing-runs/{run.json()['id']}/close",
        {"approval_id": approval.json()["id"]},
    )
    assert closed.status_code == 200, closed.text
    return owner, writer, payload["accounting_period_id"], run.json()["id"], journal, connection


def test_closed_period_generates_balanced_bs_is_and_drilldown(api_client, auth_service):
    owner, writer, period, run_id, journal, connection = closed_company(api_client, auth_service)
    key = str(uuid4())
    generated = request(
        api_client, writer, "/financial-statements/generate", {"period_id": period}, key
    )
    assert generated.status_code == 201, generated.text
    result = generated.json()
    assert result["closing_run_id"] == run_id and result["close_version"] == 1
    assert (
        request(
            api_client, writer, "/financial-statements/generate", {"period_id": period}, key
        ).json()["id"]
        == result["id"]
    )
    assert (
        api_client.get(f"/financial-statements/sets/{result['id']}", headers=owner).status_code
        == 200
    )
    bs = api_client.get(
        f"/financial-statements/sets/{result['id']}/BALANCE_SHEET", headers=owner
    ).json()
    income = api_client.get(
        f"/financial-statements/sets/{result['id']}/INCOME_STATEMENT", headers=owner
    ).json()
    by_code = {line["line_code"]: line["current_amount"] for line in bs["lines"]}
    income_by_code = {line["line_code"]: line["current_amount"] for line in income["lines"]}
    assert by_code["ASSETS"] == by_code["LIABILITIES_EQUITY"] == "100.0000"
    assert by_code["UNTRANSFERRED_PROFIT"] == income_by_code["NET_PROFIT"] == "100.0000"
    drill = api_client.get(
        f"/financial-statements/sets/{result['id']}/drilldown",
        headers=owner,
        params={"statement_type": "INCOME_STATEMENT", "line_code": "REVENUE"},
    )
    assert drill.status_code == 200 and drill.json()[0]["journal_id"] == journal["id"]
    profit_sources = api_client.get(
        f"/financial-statements/sets/{result['id']}/drilldown",
        headers=owner,
        params={"statement_type": "INCOME_STATEMENT", "line_code": "NET_PROFIT"},
    )
    assert sum(Decimal(item["amount"]) for item in profit_sources.json()) == Decimal("100")
    assert api_client.get(
        f"/financial-statements/sets/{result['id']}",
        headers={**owner, "X-Company-ID": str(uuid4())},
    ).status_code in {403, 404}
    conflict = request(
        api_client, writer, "/financial-statements/generate", {"period_id": str(uuid4())}, key
    )
    assert conflict.status_code in {404, 409}
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        sets = list(
            session.scalars(
                select(StatementSetModel).where(
                    StatementSetModel.company_id == UUID(owner["X-Company-ID"])
                )
            )
        )
        assert len(sets) == 1
        mapping = session.scalar(
            select(ReportAccountMappingModel).where(
                ReportAccountMappingModel.company_id == UUID(owner["X-Company-ID"])
            )
        )
        assert mapping is not None
        mapping.version += 1
        session.commit()
    changed = request(
        api_client, writer, "/financial-statements/generate", {"period_id": period}, key
    )
    assert changed.status_code == 409 and changed.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_changed_closing_digest_blocks_generation(api_client, auth_service):
    owner, writer, period, run_id, _, connection = closed_company(api_client, auth_service)
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        row = session.scalar(select(ClosingRunModel).where(ClosingRunModel.id == UUID(run_id)))
        assert row is not None
        row.adjusted_tb_digest = "0" * 64
        session.commit()
    failed = request(api_client, writer, "/financial-statements/generate", {"period_id": period})
    assert failed.status_code == 409 and failed.json()["code"] == "REPORT_SOURCE_STALE"


def test_posted_custom_account_without_mapping_blocks_snapshot(api_client, auth_service):
    _, writer, period, _, _, connection = closed_company(
        api_client, auth_service, custom_account=True
    )
    blocked = request(api_client, writer, "/financial-statements/generate", {"period_id": period})
    assert blocked.status_code == 422 and blocked.json()["code"] == "REPORT_MAPPING_INCOMPLETE"
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        assert session.scalar(select(StatementSetModel.id)) is None
    custom = next(
        row
        for row in api_client.get("/accounts", headers=writer).json()
        if row["account_code"] == "TEST_CUSTOM_ASSET"
    )
    mapped = api_client.post(
        "/financial-statements/mappings",
        headers=writer,
        json={"period_id": period, "account_id": custom["id"], "line_code": "ASSET_ACCOUNTS"},
    )
    assert mapped.status_code == 201, mapped.text
    generated = request(api_client, writer, "/financial-statements/generate", {"period_id": period})
    assert generated.status_code == 201, generated.text
