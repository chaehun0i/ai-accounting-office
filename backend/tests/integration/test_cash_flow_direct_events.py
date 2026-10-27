"""Evidence-backed complex cash allocation through the PostgreSQL API boundary."""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.evidence.infrastructure.models import EvidenceModel
from app.reporting.cash_flow.models import CashFlowAllocationModel
from tests.integration.test_closing_workflow import request, reviewer
from tests.integration.test_finance_flow import post_journal
from tests.integration.test_intake_api import upload
from tests.integration.test_journal_flow import prepare


def test_complex_cash_allocation_revision_and_company_isolation(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    imported = upload(api_client, writer)
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        evidence = session.scalar(
            select(EvidenceModel).where(
                EvidenceModel.company_id == UUID(owner["X-Company-ID"]),
                EvidenceModel.storage_object_id == UUID(imported["storage_object_id"]),
            )
        )
        assert evidence is not None
        evidence_id = str(evidence.id)
    accounts = {
        row["account_name"]: row["id"] for row in api_client.get("/accounts", headers=writer).json()
    }
    journal = post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": payload["accounting_period_id"],
            "entry_date": payload["entry_date"],
            "source_type": "MANUAL",
            "evidence_ids": [evidence_id],
        },
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "110.0000"},
            {"account_id": accounts["매출"], "credit_amount": "100.0000"},
            {"account_id": accounts["기타수익"], "credit_amount": "10.0000"},
        ],
    )
    run = request(
        api_client,
        writer,
        "/closing-runs",
        {"accounting_period_id": payload["accounting_period_id"]},
    )
    assert run.status_code == 201, run.text
    approval = request(
        api_client, review, f"/closing-runs/{run.json()['id']}/submit", {"reason": "월마감"}
    )
    assert approval.status_code == 200, approval.text
    assert (
        request(
            api_client,
            owner,
            f"/closing-approvals/{approval.json()['id']}/approve",
            {"reason": "확인"},
        ).status_code
        == 200
    )
    assert (
        request(
            api_client,
            owner,
            f"/closing-runs/{run.json()['id']}/close",
            {"approval_id": approval.json()["id"]},
        ).status_code
        == 200
    )
    period = next(
        row
        for row in api_client.get("/accounting/periods", headers=writer).json()
        if row["id"] == payload["accounting_period_id"]
    )
    scope = api_client.post(
        "/cash-flow/cash-scope",
        headers=writer,
        json={
            "account_id": accounts["현금및현금성자산"],
            "scope_type": "CASH",
            "effective_from": period["start_date"],
        },
    )
    assert scope.status_code == 201, scope.text
    for account, code in (("매출", "RECEIPTS"), ("기타수익", "OTHER_RECEIPTS")):
        mapped = api_client.post(
            "/cash-flow/classifications",
            headers=writer,
            json={
                "account_id": accounts[account],
                "activity_type": "OPERATING",
                "line_code": code,
                "effective_from": period["start_date"],
            },
        )
        assert mapped.status_code == 201, mapped.text
    query = {"period_id": payload["accounting_period_id"]}
    blocked = api_client.get("/cash-flow/preflight", headers=writer, params=query).json()
    assert blocked["issues"][0]["code"] == "CASH_FLOW_COMPLEX_JOURNAL"
    assert api_client.get("/cash-flow/events", headers=writer, params=query).status_code == 409
    lines = {row["account_id"]: row["id"] for row in journal["lines"]}
    cash_line = lines[accounts["현금및현금성자산"]]
    for bad_field in (
        {"evidence_id": str(uuid4())},
        {"counterpart_line_id": str(uuid4())},
    ):
        rejected = api_client.post(
            "/cash-flow/allocations",
            headers=writer,
            json={
                "journal_id": journal["id"],
                "cash_line_id": cash_line,
                "counterpart_line_id": lines[accounts["매출"]],
                "evidence_id": evidence_id,
                "amount": "100.0000",
                **bad_field,
            },
        )
        assert rejected.status_code == 422

    def allocate(account, amount):
        return api_client.post(
            "/cash-flow/allocations",
            headers=writer,
            json={
                "journal_id": journal["id"],
                "cash_line_id": cash_line,
                "counterpart_line_id": lines[accounts[account]],
                "evidence_id": evidence_id,
                "amount": amount,
            },
        )

    first = allocate("매출", "100.0000")
    assert first.status_code == 201, first.text
    assert allocate("매출", "100.0000").json()["id"] == first.json()["id"]
    incomplete = api_client.get("/cash-flow/preflight", headers=writer, params=query).json()
    assert incomplete["issues"][0]["code"] == "CASH_FLOW_ALLOCATION_INCOMPLETE"
    assert allocate("기타수익", "20.0000").status_code == 422
    assert api_client.post(
        "/cash-flow/allocations",
        headers={**writer, "X-Company-ID": str(uuid4())},
        json={
            "journal_id": journal["id"],
            "cash_line_id": cash_line,
            "counterpart_line_id": lines[accounts["기타수익"]],
            "evidence_id": evidence_id,
            "amount": "10.0000",
        },
    ).status_code in (403, 404)
    second = allocate("기타수익", "10.0000")
    assert second.status_code == 201, second.text
    ready = api_client.get("/cash-flow/preflight", headers=writer, params=query).json()
    assert ready["ready"] and ready["mapping_digest"] != blocked["mapping_digest"]
    events = api_client.get("/cash-flow/events", headers=writer, params=query)
    assert events.status_code == 200, events.text
    assert sum(Decimal(row["cash_inflow"]) for row in events.json()) == Decimal("110")
    assert all(row["evidence_id"] == evidence_id for row in events.json())
    assert api_client.get(
        "/cash-flow/events", headers={**writer, "X-Company-ID": str(uuid4())}, params=query
    ).status_code in (403, 404)
    retracted = api_client.put(
        f"/cash-flow/allocations/{first.json()['id']}",
        headers=writer,
        json={"amount": "0", "evidence_id": evidence_id},
    )
    assert retracted.status_code == 200, retracted.text
    assert (
        api_client.put(
            f"/cash-flow/allocations/{first.json()['id']}",
            headers=writer,
            json={"amount": "0", "evidence_id": evidence_id},
        ).json()["id"]
        == retracted.json()["id"]
    )
    assert (
        api_client.put(
            f"/cash-flow/allocations/{first.json()['id']}",
            headers=writer,
            json={"amount": "99.0000", "evidence_id": evidence_id},
        ).status_code
        == 409
    )
    assert allocate("매출", "100.0000").status_code == 409
    assert not api_client.get("/cash-flow/preflight", headers=writer, params=query).json()["ready"]
    restored = api_client.put(
        f"/cash-flow/allocations/{retracted.json()['id']}",
        headers=writer,
        json={"amount": "100.0000", "evidence_id": evidence_id},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["version"] == 3
    assert api_client.get("/cash-flow/preflight", headers=writer, params=query).json()["ready"]
    history = api_client.get(
        "/cash-flow/allocations", headers=writer, params={"journal_id": journal["id"]}
    )
    assert history.status_code == 200 and len(history.json()) == 4
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(CashFlowAllocationModel)
                .where(CashFlowAllocationModel.company_id == UUID(owner["X-Company-ID"]))
            )
            == 4
        )
