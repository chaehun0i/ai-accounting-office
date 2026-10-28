"""PostgreSQL bridge lifecycle: mappings, locked sources, provenance and blocking."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.companies.infrastructure.models import MembershipModel
from app.reporting.cash_flow.models import CashFlowAdjustmentRuleModel, CashFlowClassificationModel
from app.reporting.financial_statements.infrastructure.models import (
    StatementLineModel,
    StatementSetModel,
    StatementSnapshotModel,
)
from tests.integration.test_closing_workflow import request, reviewer
from tests.integration.test_finance_flow import post_journal
from tests.integration.test_financial_statements import closed_company
from tests.integration.test_journal_flow import prepare


def setup_rules(client, writer, period_id, roles):
    accounts = {
        row["account_name"]: row["id"] for row in client.get("/accounts", headers=writer).json()
    }
    period = next(
        row
        for row in client.get("/accounting/periods", headers=writer).json()
        if row["id"] == period_id
    )
    response = client.post(
        "/cash-flow/cash-scope",
        headers=writer,
        json={
            "account_id": accounts["현금및현금성자산"],
            "scope_type": "CASH",
            "effective_from": period["start_date"],
        },
    )
    assert response.status_code == 201, response.text
    for name, code, related in roles:
        payload = {
            "account_id": accounts[name],
            "adjustment_code": code,
            "source_mapping_type": "ACCOUNT_LEDGER",
            "related_account_id": accounts[related] if related else None,
            "effective_from": period["start_date"],
            "policy_code": "TAX_INTEREST_OPERATING",
            "policy_version": 1,
        }
        response = client.post("/cash-flow/adjustment-rules", headers=writer, json=payload)
        assert response.status_code == 201, response.text
        assert client.post("/cash-flow/adjustment-rules", headers=writer, json=payload).json() == (
            response.json()
        )
    return accounts, period


def classify(client, writer, accounts, period, name):
    response = client.post(
        "/cash-flow/classifications",
        headers=writer,
        json={
            "account_id": accounts[name],
            "activity_type": "OPERATING",
            "line_code": "OPERATING",
            "effective_from": period["start_date"],
        },
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    "change,issue",
    [
        ("policy", "INDIRECT_POLICY_UNSUPPORTED"),
        ("source", "INDIRECT_SOURCE_UNSUPPORTED"),
        ("statement", "INDIRECT_STATEMENT_SOURCE_STALE"),
        ("snapshot", "INDIRECT_STATEMENT_SOURCE_STALE"),
        ("amount", "INDIRECT_STATEMENT_SOURCE_STALE"),
        ("close_version", "INDIRECT_STATEMENT_SOURCE_MISSING"),
        ("direct", "INDIRECT_OPERATING_RECONCILIATION_MISMATCH"),
    ],
)
def test_bridge_ready_then_blocks_invalid_source_policy_or_reconciliation(
    api_client,
    auth_service,
    change,
    issue,
):
    owner, writer, period_id, _, journal, connection = closed_company(api_client, auth_service)
    accounts, period = setup_rules(
        api_client, writer, period_id, [("매출", "OPERATING_RESULT", None)]
    )
    classify(api_client, writer, accounts, period, "매출")
    query = {"period_id": period_id}
    missing = api_client.get("/cash-flow/indirect-bridge", headers=writer, params=query)
    assert missing.status_code == 200, missing.text
    assert missing.json()["status"] == "BLOCKED"
    assert missing.json()["net_profit"] is None
    generated = request(api_client, writer, "/financial-statements/generate", query)
    assert generated.status_code == 201, generated.text
    response = api_client.get("/cash-flow/indirect-bridge", headers=writer, params=query)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "READY", result
    assert Decimal(result["net_profit"]) == Decimal(result["net_operating"]) == Decimal("100")
    assert result["statement_set_id"] == generated.json()["id"]
    assert result["adjustments"][0]["sources"][0]["journal_id"] == journal["id"]
    assert (
        api_client.get("/cash-flow/indirect-bridge", headers=writer, params=query).json() == result
    )
    assert api_client.get(
        "/cash-flow/indirect-bridge", headers={**owner, "X-Company-ID": str(uuid4())}, params=query
    ).status_code in (403, 404)
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        if change in {"statement", "close_version"}:
            row = session.get(StatementSetModel, UUID(generated.json()["id"]))
            if change == "statement":
                row.mapping_digest = "0" * 64
            else:
                row.close_version += 1
        elif change == "snapshot":
            row = session.scalar(
                select(StatementSnapshotModel).where(
                    StatementSnapshotModel.company_id == UUID(writer["X-Company-ID"])
                )
            )
            row.source_digest = "0" * 64
        elif change == "amount":
            row = session.scalar(
                select(StatementLineModel).where(
                    StatementLineModel.company_id == UUID(writer["X-Company-ID"])
                )
            )
            row.current_amount += Decimal("1")
        elif change == "direct":
            row = session.scalar(
                select(CashFlowClassificationModel).where(
                    CashFlowClassificationModel.account_id == UUID(accounts["매출"])
                )
            )
            row.activity_type = "FINANCING"
        else:
            row = session.scalar(
                select(CashFlowAdjustmentRuleModel).where(
                    CashFlowAdjustmentRuleModel.account_id == UUID(accounts["매출"])
                )
            )
            if change == "policy":
                row.policy_version = 2
            else:
                row.source_mapping_type = "ASSET_REGISTER"
        session.commit()
    blocked = api_client.get("/cash-flow/indirect-bridge", headers=writer, params=query).json()
    assert blocked["status"] == "BLOCKED"
    assert issue in {item["code"] for item in blocked["issues"]}
    if change == "direct":
        assert Decimal(blocked["reconciliation_difference"]) == Decimal("100")
        assert Decimal(blocked["net_operating"]) == Decimal("100")


def test_rule_company_scope_permissions_and_immutable_v1(api_client, auth_service):
    owner, writer, period_id, _, _, connection = closed_company(api_client, auth_service)
    accounts, period = setup_rules(
        api_client, writer, period_id, [("매출", "OPERATING_RESULT", None)]
    )
    payload = {
        "account_id": accounts["매출"],
        "adjustment_code": "OPERATING_RESULT",
        "source_mapping_type": "ACCOUNT_LEDGER",
        "effective_from": period["start_date"],
        "policy_code": "TAX_INTEREST_OPERATING",
        "policy_version": 1,
    }
    assert (
        api_client.post(
            "/cash-flow/adjustment-rules",
            headers=writer,
            json={**payload, "source_mapping_type": "ASSET_REGISTER"},
        ).status_code
        == 409
    )
    other = api_client.post(
        "/companies",
        headers=owner,
        json={
            "company_name": "격리 회사",
            "business_number": "9876543210",
            "taxpayer_type": "INDIVIDUAL",
            "opening_date": "2026-01-01",
            "address": "테스트",
        },
    )
    assert other.status_code == 201, other.text
    other_headers = {**owner, "X-Company-ID": other.json()["id"]}
    assert (
        api_client.post(
            "/cash-flow/adjustment-rules", headers=other_headers, json=payload
        ).status_code
        == 404
    )
    assert api_client.get("/cash-flow/adjustment-rules", headers=other_headers).json() == []
    assert (
        api_client.get(
            "/cash-flow/indirect-bridge", headers=other_headers, params={"period_id": period_id}
        ).status_code
        == 404
    )
    writer_id = api_client.get("/auth/me", headers=writer).json()["id"]
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        membership = session.scalar(
            select(MembershipModel).where(
                MembershipModel.company_id == UUID(writer["X-Company-ID"]),
                MembershipModel.user_id == UUID(writer_id),
            )
        )
        membership.role_code = "VIEWER"
        session.commit()
    assert (
        api_client.post("/cash-flow/adjustment-rules", headers=writer, json=payload).status_code
        == 403
    )
    assert api_client.get("/cash-flow/adjustment-rules", headers=writer).status_code == 200
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        membership = session.scalar(
            select(MembershipModel).where(
                MembershipModel.company_id == UUID(writer["X-Company-ID"]),
                MembershipModel.user_id == UUID(writer_id),
            )
        )
        membership.status = "REVOKED"
        membership.revoked_at = datetime.now(UTC)
        session.commit()
    assert (
        api_client.get(
            "/cash-flow/indirect-bridge", headers=writer, params={"period_id": period_id}
        ).status_code
        == 404  # revoked membership is masked as an inaccessible company
    )


def test_closed_ledger_non_cash_ar_ap_bridge(api_client, auth_service):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    # Default AR/AP are subledger control accounts; this fixture exercises explicit
    # ledger-only WC sources without bypassing their closing reconciliation.
    for code, name, kind, line in (
        ("BRIDGE_AR", "Bridge receivable", "ASSET", "ASSET_ACCOUNTS"),
        ("BRIDGE_AP", "Bridge payable", "LIABILITY", "LIABILITY_ACCOUNTS"),
    ):
        created = api_client.post(
            "/accounts",
            headers=writer,
            json={
                "account_code": code,
                "account_name": name,
                "account_type": kind,
            },
        )
        assert created.status_code == 201, created.text
        mapped = api_client.post(
            "/financial-statements/mappings",
            headers=writer,
            json={
                "period_id": payload["accounting_period_id"],
                "account_id": created.json()["id"],
                "line_code": line,
            },
        )
        assert mapped.status_code == 201, mapped.text
    accounts = {
        row["account_name"]: row["id"] for row in api_client.get("/accounts", headers=writer).json()
    }
    for debit, credit, amount in [
        ("Bridge receivable", "매출", "100"),
        ("현금및현금성자산", "Bridge receivable", "70"),
        ("소모품비", "Bridge payable", "30"),
        ("Bridge payable", "현금및현금성자산", "20"),
        ("감가상각비", "감가상각누계액", "10"),
    ]:
        post_journal(
            api_client,
            owner,
            writer,
            {
                "accounting_period_id": payload["accounting_period_id"],
                "entry_date": payload["entry_date"],
                "source_type": "MANUAL",
            },
            [
                {"account_id": accounts[debit], "debit_amount": amount},
                {"account_id": accounts[credit], "credit_amount": amount},
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
    closed = request(
        api_client,
        owner,
        f"/closing-runs/{run.json()['id']}/close",
        {"approval_id": approval.json()["id"]},
    )
    assert closed.status_code == 200, closed.text
    period_id = payload["accounting_period_id"]
    accounts, period = setup_rules(
        api_client,
        writer,
        period_id,
        [
            ("매출", "OPERATING_RESULT", None),
            ("소모품비", "OPERATING_RESULT", None),
            ("Bridge receivable", "WORKING_CAPITAL", None),
            ("Bridge payable", "WORKING_CAPITAL", None),
            ("감가상각비", "NONCASH_PAIR", "감가상각누계액"),
            ("감가상각누계액", "EXCLUDED_BALANCE", None),
        ],
    )
    for name in ("Bridge receivable", "Bridge payable"):
        classify(api_client, writer, accounts, period, name)
    query = {"period_id": period_id}
    generated = request(api_client, writer, "/financial-statements/generate", query)
    assert generated.status_code == 201, generated.text
    response = api_client.get("/cash-flow/indirect-bridge", headers=writer, params=query)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "READY", result
    assert Decimal(result["net_profit"]) == Decimal("60")
    assert Decimal(result["net_operating"]) == Decimal("50")
    assert Decimal(result["direct_net_operating"]) == Decimal("50")
    assert Decimal(result["reconciliation_difference"]) == Decimal("0")
    adjusted = {row["account_id"]: row for row in result["adjustments"]}
    assert Decimal(adjusted[accounts["Bridge receivable"]]["amount"]) == Decimal("-30")
    assert Decimal(adjusted[accounts["Bridge payable"]]["amount"]) == Decimal("10")
    assert Decimal(adjusted[accounts["감가상각비"]]["amount"]) == Decimal("10")
