"""CLOSED BS/IS to frozen SCE, provenance and company isolation."""

from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.reporting.disclosures.models import (
    DisclosureInstanceModel,
    DisclosureNarrativeModel,
    DisclosureValueModel,
)
from app.reporting.equity.models import EquityStatementModel
from tests.integration.test_closing_workflow import request, reviewer
from tests.integration.test_finance_flow import post_journal
from tests.integration.test_journal_flow import prepare


def close(client, owner, writer, review, period_id):
    run = request(client, writer, "/closing-runs", {"accounting_period_id": period_id})
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
    result = request(
        client,
        owner,
        f"/closing-runs/{run.json()['id']}/close",
        {"approval_id": approval.json()["id"]},
    )
    assert result.status_code == 200, result.text


@pytest.mark.parametrize("physical_transfer", [False, True])
def test_equity_rollforward_uses_prior_bs_and_current_is(
    api_client, auth_service, physical_transfer, concurrent=False
):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    review = reviewer(api_client, owner, connection)
    open_readiness = api_client.get(
        "/equity/reconciliation",
        headers=writer,
        params={"period_id": payload["accounting_period_id"]},
    )
    assert open_readiness.status_code == 200, open_readiness.text
    assert open_readiness.json()["issues"] == ["PERIOD_NOT_CLOSED"]
    assert open_readiness.json()["income_statement_profit"] is None
    foreign = api_client.get(
        "/equity/reconciliation",
        headers={**writer, "X-Company-ID": str(uuid4())},
        params={"period_id": payload["accounting_period_id"]},
    )
    assert foreign.status_code in {403, 404}
    periods = api_client.get("/closing/periods", headers=writer).json()
    january = next(p for p in periods if p["period_no"] == 1)
    february = next(p for p in periods if p["period_no"] == 2)
    accounts = {
        a["account_name"]: a["id"] for a in api_client.get("/accounts", headers=writer).json()
    }
    capital = post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": january["id"],
            "entry_date": "2026-01-02",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "200.0000"},
            {"account_id": accounts["자본금"], "credit_amount": "200.0000"},
        ],
    )
    post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": january["id"],
            "entry_date": "2026-01-03",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "100.0000"},
            {"account_id": accounts["매출"], "credit_amount": "100.0000"},
        ],
    )
    close(api_client, owner, writer, review, january["id"])
    assert (
        request(
            api_client, writer, "/financial-statements/generate", {"period_id": january["id"]}
        ).status_code
        == 201
    )
    post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": february["id"],
            "entry_date": "2026-02-03",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "50.0000"},
            {"account_id": accounts["매출"], "credit_amount": "50.0000"},
        ],
    )
    contribution = post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": february["id"],
            "entry_date": "2026-02-04",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["현금및현금성자산"], "debit_amount": "25.0000"},
            {"account_id": accounts["자본금"], "credit_amount": "25.0000"},
        ],
    )
    transfer = None
    if physical_transfer:
        transfer = post_journal(
            api_client,
            owner,
            writer,
            {
                "accounting_period_id": february["id"],
                "entry_date": "2026-02-04",
                "source_type": "MANUAL",
            },
            [
                {"account_id": accounts["매출"], "debit_amount": "100.0000"},
                {"account_id": accounts["미처분이익잉여금"], "credit_amount": "100.0000"},
            ],
        )
    dividend = post_journal(
        api_client,
        owner,
        writer,
        {
            "accounting_period_id": february["id"],
            "entry_date": "2026-02-05",
            "source_type": "MANUAL",
        },
        [
            {"account_id": accounts["미처분이익잉여금"], "debit_amount": "10.0000"},
            {"account_id": accounts["미지급배당금"], "credit_amount": "10.0000"},
        ],
    )
    close(api_client, owner, writer, review, february["id"])
    assert (
        request(
            api_client, writer, "/financial-statements/generate", {"period_id": february["id"]}
        ).status_code
        == 201
    )
    retained = api_client.post(
        "/equity/components",
        headers=writer,
        json={
            "component_code": "RETAINED",
            "name": "이익잉여금",
            "component_type": "RETAINED_EARNINGS",
            "display_order": 2,
        },
    )
    assert retained.status_code == 201, retained.text
    contributed = api_client.post(
        "/equity/components",
        headers=writer,
        json={
            "component_code": "CAPITAL",
            "name": "납입자본",
            "component_type": "CONTRIBUTED_CAPITAL",
            "display_order": 1,
        },
    )
    assert contributed.status_code == 201, contributed.text
    blocked = api_client.get(
        "/equity/reconciliation", headers=owner, params={"period_id": february["id"]}
    )
    assert blocked.status_code == 200 and blocked.json()["status"] == "BLOCKED"
    assert "EQUITY_MAPPING_INCOMPLETE" in blocked.json()["issues"]
    mapped = api_client.post(
        "/equity/mappings",
        headers=writer,
        json={
            "component_id": contributed.json()["id"],
            "account_id": accounts["자본금"],
            "effective_from": "2026-01-01",
        },
    )
    assert mapped.status_code == 201, mapped.text
    retained_mapping = api_client.post(
        "/equity/mappings",
        headers=writer,
        json={
            "component_id": retained.json()["id"],
            "account_id": accounts["미처분이익잉여금"],
            "effective_from": "2026-01-01",
        },
    )
    assert retained_mapping.status_code == 201, retained_mapping.text
    unclassified = api_client.get(
        "/equity/reconciliation", headers=owner, params={"period_id": february["id"]}
    )
    assert "UNCLASSIFIED_EQUITY_SOURCE" in unclassified.json()["issues"]
    source_candidates = api_client.get(
        "/equity/dividend-sources", headers=writer, params={"period_id": february["id"]}
    )
    assert source_candidates.status_code == 200, source_candidates.text
    source = next(row for row in source_candidates.json() if row["journal_id"] == dividend["id"])
    assert source["status"] == "AVAILABLE" and Decimal(source["amount"]) == Decimal("10")
    assert (
        api_client.get(
            "/equity/dividend-sources",
            headers={**writer, "X-Company-ID": str(uuid4())},
            params={"period_id": february["id"]},
        ).status_code
        == 404
    )
    declaration_payload = {
        "resolution_date": "2026-02-04",
        "payable_date": "2026-03-10",
        "total_amount": "10.0000",
        "source_journal_id": dividend["id"],
    }
    if concurrent:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: api_client.post(
                        "/equity/dividends", headers=writer, json=declaration_payload
                    ),
                    range(2),
                )
            )
        assert all(row.status_code == 201 for row in responses)
        assert responses[0].json()["id"] == responses[1].json()["id"]
        declared = responses[0]
    else:
        declared = api_client.post("/equity/dividends", headers=writer, json=declaration_payload)
    assert declared.status_code == 201, declared.text
    declaration_payload = {
        "resolution_date": "2026-02-04",
        "payable_date": "2026-03-10",
        "total_amount": "10.0000",
        "source_journal_id": dividend["id"],
    }
    replay_declaration = api_client.post(
        "/equity/dividends", headers=writer, json=declaration_payload
    )
    assert (
        replay_declaration.status_code == 201
        and replay_declaration.json()["id"] == declared.json()["id"]
    )
    assert (
        api_client.post(
            "/equity/dividends",
            headers=writer,
            json={**declaration_payload, "payable_date": "2026-03-11"},
        ).status_code
        == 409
    )
    source_candidates = api_client.get(
        "/equity/dividend-sources", headers=writer, params={"period_id": february["id"]}
    ).json()
    assert (
        next(row for row in source_candidates if row["journal_id"] == dividend["id"])["status"]
        == "LINKED"
    )
    from app.reporting.equity.models import DividendDeclarationModel

    with Session(connection, join_transaction_mode="create_savepoint") as session:
        existing = session.get(DividendDeclarationModel, UUID(declared.json()["id"]))
        assert existing is not None
        with pytest.raises(IntegrityError):
            session.add(
                DividendDeclarationModel(
                    **{
                        column.name: uuid4()
                        if column.name == "id"
                        else getattr(existing, column.name)
                        for column in DividendDeclarationModel.__table__.columns
                    }
                )
            )
            session.flush()
        session.rollback()
    missing_cf = api_client.get(
        f"/equity/dividends/{declared.json()['id']}/payment-sources",
        headers=writer,
        params={"period_id": february["id"]},
    )
    assert missing_cf.status_code == 200 and missing_cf.json()["issue"] == "CF_SNAPSHOT_MISSING"
    assert (
        api_client.get(f"/equity/dividends/{declared.json()['id']}/payments", headers=owner).json()
        == []
    )
    for journal, account_id, kind in [
        (contribution, accounts["자본금"], "CAPITAL_CONTRIBUTION"),
        (dividend, accounts["미처분이익잉여금"], "DIVIDEND"),
    ]:
        line_id = next(line["id"] for line in journal["lines"] if line["account_id"] == account_id)
        classified = api_client.post(
            "/equity/events", headers=writer, json={"journal_line_id": line_id, "event_type": kind}
        )
        assert classified.status_code == 201, classified.text
    if transfer:
        transfer_line = next(
            line["id"]
            for line in transfer["lines"]
            if line["account_id"] == accounts["미처분이익잉여금"]
        )
        classified = api_client.post(
            "/equity/events",
            headers=writer,
            json={"journal_line_id": transfer_line, "event_type": "PROFIT_TRANSFER"},
        )
        assert classified.status_code == 201, classified.text
    ready = api_client.get(
        "/equity/reconciliation", headers=owner, params={"period_id": february["id"]}
    )
    assert ready.status_code == 200, ready.text
    if transfer:
        assert ready.json()["status"] == "BLOCKED", ready.json()
        assert "PROFIT_TRANSFER_IS_MISMATCH" in ready.json()["issues"]
        assert Decimal(ready.json()["income_statement_profit"]) == Decimal("-50")
        check = next(
            row for row in ready.json()["checks"] if row["code"] == "PROFIT_TRANSFER_IS_MISMATCH"
        )
        assert check["status"] == "BLOCKED"
        assert Decimal(check["reported_amount"]) == Decimal("-50")
        assert Decimal(check["source_amount"]) == Decimal("50")
        assert Decimal(check["difference"]) == Decimal("100")
        assert check["journal_ids"] == [transfer["id"]]
        assert check["next_action"] == "REVIEW_HARD_CLOSE_CONTRACT"
        source_rows = [
            row for row in ready.json()["source_rows"] if row["journal_id"] == transfer["id"]
        ]
        assert {row["journal_line_id"] for row in source_rows} == {
            row["id"] for row in transfer["lines"]
        }
        assert sum((Decimal(row["amount"]) for row in source_rows), Decimal("0")) == 0
        assert ready.json()["close_version"] == 1
        assert ready.json()["statement_set_id"] is not None
        assert (
            request(
                api_client, writer, "/equity/statements/generate", {"period_id": february["id"]}
            ).status_code
            == 422
        )
        return
    assert ready.json()["status"] == "READY", ready.json()
    assert Decimal(ready.json()["balance_sheet_equity"]) == Decimal("365")
    assert Decimal(ready.json()["income_statement_profit"]) == Decimal("50")
    assert Decimal(ready.json()["rollforward_equity"]) == Decimal("365")
    assert ready.json()["checks"][0]["status"] == "MATCHED"
    assert Decimal(ready.json()["checks"][0]["difference"]) == 0
    assert all(not row["classification_required"] for row in ready.json()["source_rows"])
    key = str(uuid4())
    generated = request(
        api_client, writer, "/equity/statements/generate", {"period_id": february["id"]}, key
    )
    assert generated.status_code == 201, generated.text
    replay = request(
        api_client, writer, "/equity/statements/generate", {"period_id": february["id"]}, key
    )
    assert replay.status_code == 201 and replay.json()["id"] == generated.json()["id"]
    detail = api_client.get(f"/equity/statements/{generated.json()['id']}", headers=owner)
    assert detail.status_code == 200
    lines = {(line["component_id"], line["movement_type"]): line for line in detail.json()["lines"]}
    assert Decimal(lines[(retained.json()["id"], "OPENING")]["amount"]) == Decimal("100")
    assert Decimal(lines[(retained.json()["id"], "PROFIT_OR_LOSS")]["amount"]) == Decimal("50")
    assert Decimal(lines[(contributed.json()["id"], "CLOSING")]["amount"]) == Decimal("225")
    assert Decimal(lines[(retained.json()["id"], "OWNER_TRANSACTIONS")]["amount"]) == Decimal("-10")
    opening_line = lines[(contributed.json()["id"], "OPENING")]
    sources = api_client.get(
        f"/equity/statements/{generated.json()['id']}/lines/{opening_line['id']}/sources",
        headers=owner,
    )
    assert sources.status_code == 200 and sources.json()[0]["journal_id"] == capital["id"]
    assert api_client.get(
        f"/equity/statements/{generated.json()['id']}",
        headers={**owner, "X-Company-ID": str(uuid4())},
    ).status_code in {403, 404}
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        with pytest.raises(IntegrityError):
            session.execute(
                update(EquityStatementModel)
                .where(EquityStatementModel.id == UUID(generated.json()["id"]))
                .values(status="RECONCILED")
            )
        session.rollback()

    review_path = f"/equity/statements/{generated.json()['id']}/review"
    state = api_client.get(review_path, headers=writer)
    assert state.status_code == 200 and state.json()["version"] == 0
    assert (
        api_client.get(review_path, headers={**writer, "X-Company-ID": str(uuid4())}).status_code
        == 404
    )
    unapproved = request(
        api_client,
        writer,
        "/reports/generations",
        {
            "report_code": "CHANGES_IN_EQUITY",
            "format": "CSV",
            "period_id": february["id"],
            "period_preset": "CUSTOM",
            "date_from": february["start_date"],
            "date_to": february["end_date"],
        },
    )
    assert unapproved.status_code == 409, unapproved.text
    owner_request = request(
        api_client,
        owner,
        review_path + "/request-review",
        {"expected_version": 0, "reason": "검토 요청"},
    )
    assert owner_request.status_code == 200, owner_request.text
    assert (
        request(
            api_client,
            owner,
            review_path + "/approve",
            {"expected_version": 1, "reason": "요청자 자가 승인"},
        ).status_code
        == 409
    )
    rejected = request(
        api_client,
        review,
        review_path + "/reject",
        {"expected_version": 1, "reason": "근거 재확인"},
    )
    assert rejected.status_code == 200, rejected.text
    requested_key = str(uuid4())
    review_payload = {"expected_version": 2, "reason": "원천과 대사 확인"}
    requested = request(
        api_client, writer, review_path + "/request-review", review_payload, requested_key
    )
    assert requested.status_code == 200, requested.text
    replay_review = request(
        api_client, writer, review_path + "/request-review", review_payload, requested_key
    )
    assert replay_review.json()["id"] == requested.json()["id"]
    assert (
        request(
            api_client,
            writer,
            review_path + "/request-review",
            {**review_payload, "reason": "변경"},
            requested_key,
        ).status_code
        == 409
    )
    assert (
        request(
            api_client, owner, review_path + "/approve", {"expected_version": 0, "reason": "구버전"}
        ).status_code
        == 409
    )
    assert (
        request(
            api_client,
            writer,
            review_path + "/approve",
            {"expected_version": 1, "reason": "자가 승인"},
        ).status_code
        == 403
    )
    if concurrent:
        from tests.integration.test_business_document_concurrency import parallel

        results = parallel(
            lambda _: request(
                api_client,
                owner,
                review_path + "/approve",
                {"expected_version": 3, "reason": "독립 검토 완료"},
            )
        )
        assert sorted(row.status_code for row in results) == [200, 409]
        approved = next(row for row in results if row.status_code == 200)
    else:
        approved = request(
            api_client,
            owner,
            review_path + "/approve",
            {"expected_version": 3, "reason": "독립 검토 완료"},
        )
    if concurrent:
        # Replay a completed approval concurrently: neither request may append another event.
        from tests.integration.test_business_document_concurrency import parallel

        replay_key = str(uuid4())
        results = parallel(
            lambda _: request(
                api_client,
                owner,
                review_path + "/approve",
                {"expected_version": 3, "reason": "경합"},
                replay_key,
            )
        )
        assert sorted(row.status_code for row in results) == [409, 409]
    assert approved.status_code == 200, approved.text
    assert approved.json()["source_digest"] == generated.json()["snapshot_digest"]
    equity_approval_id = approved.json()["id"]
    assert (
        request(
            api_client,
            owner,
            review_path + "/approve",
            {"expected_version": 4, "reason": "중복 승인"},
        ).status_code
        == 409
    )
    from app.reporting.equity.review_models import EquityReviewModel

    with Session(connection, join_transaction_mode="create_savepoint") as session:
        with pytest.raises(IntegrityError):
            session.execute(
                update(EquityReviewModel)
                .where(EquityReviewModel.id == UUID(approved.json()["id"]))
                .values(reason="변조")
            )
        session.rollback()

    march = next(p for p in periods if p["period_no"] == 3)
    first_payment = post_journal(
        api_client,
        owner,
        writer,
        {"accounting_period_id": march["id"], "entry_date": "2026-03-04", "source_type": "MANUAL"},
        [
            {"account_id": accounts["미지급배당금"], "debit_amount": "5.0000"},
            {"account_id": accounts["현금및현금성자산"], "credit_amount": "5.0000"},
        ],
    )
    excess_payment = post_journal(
        api_client,
        owner,
        writer,
        {"accounting_period_id": march["id"], "entry_date": "2026-03-05", "source_type": "MANUAL"},
        [
            {"account_id": accounts["미지급배당금"], "debit_amount": "6.0000"},
            {"account_id": accounts["현금및현금성자산"], "credit_amount": "6.0000"},
        ],
    )
    close(api_client, owner, writer, review, march["id"])
    assert (
        request(
            api_client, writer, "/financial-statements/generate", {"period_id": march["id"]}
        ).status_code
        == 201
    )
    assert (
        api_client.post(
            "/cash-flow/cash-scope",
            headers=writer,
            json={
                "account_id": accounts["현금및현금성자산"],
                "scope_type": "CASH",
                "effective_from": "2026-01-01",
            },
        ).status_code
        == 201
    )
    assert (
        api_client.post(
            "/cash-flow/classifications",
            headers=writer,
            json={
                "account_id": accounts["미지급배당금"],
                "activity_type": "FINANCING",
                "line_code": "DIVIDENDS_PAID",
                "effective_from": "2026-03-01",
            },
        ).status_code
        == 201
    )
    assert (
        api_client.post(
            "/cash-flow/adjustment-rules",
            headers=writer,
            json={
                "account_id": accounts["미지급배당금"],
                "adjustment_code": "EXCLUDED_BALANCE",
                "source_mapping_type": "ACCOUNT_LEDGER",
                "related_account_id": None,
                "effective_from": "2026-03-01",
                "policy_code": "TAX_INTEREST_OPERATING",
                "policy_version": 1,
            },
        ).status_code
        == 201
    )
    bridge = api_client.get(
        "/cash-flow/indirect-bridge", headers=writer, params={"period_id": march["id"]}
    )
    assert bridge.status_code == 200 and bridge.json()["status"] == "READY", bridge.text
    cf_payload = {
        key: bridge.json()[key]
        for key in (
            "period_id",
            "statement_set_id",
            "close_version",
            "source_digest",
            "mapping_digest",
        )
    }
    cash_flow = request(api_client, writer, "/cash-flow/generate", cf_payload)
    assert cash_flow.status_code == 201, cash_flow.text
    events = api_client.get(
        f"/cash-flow/{cash_flow.json()['id']}/drilldown", headers=writer
    ).json()["events"]
    event_ids = {event["journal_id"]: event["id"] for event in events}
    assert set(event_ids) == {first_payment["id"], excess_payment["id"]}
    payment_url = f"/equity/dividends/{declared.json()['id']}/payments"
    choices_url = f"/equity/dividends/{declared.json()['id']}/payment-sources"
    choices = api_client.get(choices_url, headers=writer, params={"period_id": march["id"]})
    assert choices.status_code == 200, choices.text
    assert Decimal(choices.json()["remaining_amount"]) == Decimal("10")
    assert all(row["status"] == "AVAILABLE" for row in choices.json()["candidates"])
    assert (
        api_client.get(
            choices_url,
            headers={**writer, "X-Company-ID": str(uuid4())},
            params={"period_id": march["id"]},
        ).status_code
        == 404
    )
    if concurrent:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: api_client.post(
                        payment_url,
                        headers=writer,
                        json={"cash_flow_event_id": event_ids[first_payment["id"]]},
                    ),
                    range(2),
                )
            )
        assert all(row.status_code == 201 for row in responses)
        assert responses[0].json()["id"] == responses[1].json()["id"]
        paid = responses[0]
    else:
        paid = api_client.post(
            payment_url, headers=writer, json={"cash_flow_event_id": event_ids[first_payment["id"]]}
        )
    assert paid.status_code == 201, paid.text
    assert Decimal(paid.json()["amount"]) == Decimal("5")
    choices = api_client.get(choices_url, headers=writer, params={"period_id": march["id"]}).json()
    assert Decimal(choices["paid_amount"]) == Decimal("5")
    assert Decimal(choices["remaining_amount"]) == Decimal("5")
    issues = {row["journal_id"]: row["issue"] for row in choices["candidates"]}
    assert issues[first_payment["id"]] == "PAYMENT_ALREADY_LINKED"
    assert issues[excess_payment["id"]] == "PAYMENT_EXCEEDS_DECLARATION"
    replayed_payment = api_client.post(
        payment_url, headers=writer, json={"cash_flow_event_id": event_ids[first_payment["id"]]}
    )
    assert (
        replayed_payment.status_code == 201 and replayed_payment.json()["id"] == paid.json()["id"]
    )
    blocked_payment = api_client.post(
        payment_url, headers=writer, json={"cash_flow_event_id": event_ids[excess_payment["id"]]}
    )
    assert blocked_payment.status_code == 409, blocked_payment.text
    assert len(api_client.get(payment_url, headers=writer).json()) == 1
    assert api_client.post(
        payment_url,
        headers={**writer, "X-Company-ID": str(uuid4())},
        json={"cash_flow_event_id": event_ids[first_payment["id"]]},
    ).status_code in {403, 404}

    march_equity_ready = api_client.get(
        "/equity/reconciliation", headers=writer, params={"period_id": march["id"]}
    )
    assert march_equity_ready.status_code == 200, march_equity_ready.text
    assert march_equity_ready.json()["status"] == "READY", march_equity_ready.json()
    march_equity = request(
        api_client, writer, "/equity/statements/generate", {"period_id": march["id"]}
    )
    assert march_equity.status_code == 201, march_equity.text

    notes_ready = api_client.get(
        "/disclosures/readiness", headers=owner, params={"period_id": march["id"]}
    )
    assert notes_ready.status_code == 200, notes_ready.text
    assert notes_ready.json()["status"] == "READY", notes_ready.json()
    template = api_client.get("/disclosures/templates", headers=owner)
    assert template.status_code == 200, template.text
    sections = template.json()[0]["sections"]
    notes_key = str(uuid4())
    notes = request(
        api_client,
        owner,
        "/disclosures/instances/generate",
        {"period_id": march["id"]},
        notes_key,
    )
    assert notes.status_code == 201, notes.text
    notes_instance = notes.json()
    assert notes_instance["status"] == "DRAFT"
    assert notes_instance["reconciliation_status"] == "RECONCILED"
    assert len(notes_instance["values"]) > len(sections)
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        original_instance = session.get(DisclosureInstanceModel, UUID(notes_instance["id"]))
        assert original_instance is not None
        with pytest.raises(IntegrityError):
            session.add(
                DisclosureInstanceModel(
                    id=uuid4(),
                    company_id=original_instance.company_id,
                    statement_set_id=original_instance.statement_set_id,
                    period_id=original_instance.period_id,
                    template_id=original_instance.template_id,
                    template_version=original_instance.template_version,
                    revision=original_instance.revision,
                    status="DRAFT",
                    balance_sheet_digest=original_instance.balance_sheet_digest,
                    income_statement_digest=original_instance.income_statement_digest,
                    cash_flow_digest=original_instance.cash_flow_digest,
                    equity_digest=original_instance.equity_digest,
                    source_digest=original_instance.source_digest,
                    reconciliation_status=original_instance.reconciliation_status,
                    reconciliation_digest=original_instance.reconciliation_digest,
                    created_by=original_instance.created_by,
                    created_at=original_instance.created_at,
                    approved_by=None,
                    approved_at=None,
                    version=original_instance.version,
                )
            )
            session.flush()
        session.rollback()
    account_facts = [
        value
        for value in notes_instance["values"]
        if value.get("account_id") and Decimal(value["decimal_value"]) != 0
    ]
    assert account_facts
    account_fact = account_facts[0]
    account_source = api_client.get(
        f"/disclosures/instances/{notes_instance['id']}/values/{account_fact['id']}/source",
        headers=writer,
    )
    assert account_source.status_code == 200, account_source.text
    assert account_source.json()["account_id"] == account_fact["account_id"]
    assert account_source.json()["journal_line_ids"]
    assert account_source.json()["amount"] == account_fact["decimal_value"]
    replay = request(
        api_client,
        owner,
        "/disclosures/instances/generate",
        {"period_id": march["id"]},
        notes_key,
    )
    assert replay.status_code == 201 and replay.json()["id"] == notes_instance["id"]
    conflicting_replay = request(
        api_client,
        owner,
        "/disclosures/instances/generate",
        {"period_id": february["id"]},
        notes_key,
    )
    assert conflicting_replay.status_code == 409, conflicting_replay.text
    source_value = next(
        value for value in notes_instance["values"] if value["source_type"] == "BALANCE_SHEET"
    )
    source = api_client.get(
        f"/disclosures/instances/{notes_instance['id']}/values/{source_value['id']}/source",
        headers=owner,
    )
    assert source.status_code == 200, source.text
    assert source.json()["source_id"] == source_value["source_id"]
    assert source.json()["source_path"].startswith("/financial-statements/sets/")
    assert api_client.get(
        f"/disclosures/instances/{notes_instance['id']}/values/{source_value['id']}/source",
        headers={**writer, "X-Company-ID": str(uuid4())},
    ).status_code in {403, 404}

    instance_version = notes_instance["version"]
    for section in sections:
        saved = api_client.put(
            f"/disclosures/instances/{notes_instance['id']}/narratives",
            headers=owner,
            json={
                "section_id": section["id"],
                "text_value": f"{section['title']}의 검증된 Fact를 검토했습니다.",
                "expected_version": instance_version,
            },
        )
        assert saved.status_code == 200, saved.text
        instance_version = saved.json()["instance_version"]
    stale_review = api_client.post(
        f"/disclosures/instances/{notes_instance['id']}/request-review",
        headers=owner,
        json={"expected_version": notes_instance["version"]},
    )
    assert stale_review.status_code == 409, stale_review.text
    requested = api_client.post(
        f"/disclosures/instances/{notes_instance['id']}/request-review",
        headers=owner,
        json={"expected_version": instance_version},
    )
    assert requested.status_code == 200, requested.text
    assert requested.json()["status"] == "REVIEW_REQUESTED"
    assert (
        api_client.post(
            f"/disclosures/instances/{notes_instance['id']}/approve",
            headers=owner,
            json={"expected_version": instance_version},
        ).status_code
        == 409
    )
    assert (
        api_client.post(
            f"/disclosures/instances/{notes_instance['id']}/approve",
            headers=writer,
            json={"expected_version": requested.json()["version"]},
        ).status_code
        == 403
    )
    rejected = api_client.post(
        f"/disclosures/instances/{notes_instance['id']}/reject",
        headers=review,
        json={"expected_version": requested.json()["version"], "reason": "표현 보완"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    revised_narrative = api_client.put(
        f"/disclosures/instances/{notes_instance['id']}/narratives",
        headers=owner,
        json={
            "section_id": sections[0]["id"],
            "text_value": "검토 의견을 반영해 원천을 다시 확인했습니다.",
            "expected_version": rejected.json()["version"],
        },
    )
    assert revised_narrative.status_code == 200, revised_narrative.text
    requested_again = api_client.post(
        f"/disclosures/instances/{notes_instance['id']}/request-review",
        headers=owner,
        json={"expected_version": revised_narrative.json()["instance_version"]},
    )
    assert requested_again.status_code == 200, requested_again.text
    approved = api_client.post(
        f"/disclosures/instances/{notes_instance['id']}/approve",
        headers=review,
        json={"expected_version": requested_again.json()["version"]},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approved_by"] != approved.json()["created_by"]
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        with pytest.raises(ProgrammingError):
            session.execute(
                update(DisclosureValueModel)
                .where(DisclosureValueModel.id == UUID(source_value["id"]))
                .values(decimal_value=Decimal("0"))
            )
        session.rollback()
        with pytest.raises(ProgrammingError):
            session.execute(
                update(DisclosureNarrativeModel)
                .where(
                    DisclosureNarrativeModel.instance_id == UUID(notes_instance["id"]),
                    DisclosureNarrativeModel.section_id == UUID(sections[0]["id"]),
                )
                .values(text_value="변경 불가")
            )
        session.rollback()

    for report_format in ("CSV", "XLSX", "PDF"):
        report = api_client.post(
            "/reports/generations",
            headers={**writer, "Idempotency-Key": str(uuid4())},
            json={
                "report_code": "NOTES",
                "format": report_format,
                "period_id": march["id"],
                "period_preset": "CUSTOM",
                "date_from": march["start_date"],
                "date_to": march["end_date"],
            },
        )
        assert report.status_code == 201, report.text
        assert report.json()["source_digest"] == notes_instance["source_digest"]
        assert report.json()["status"] == "COMPLETED", report.text
        artifact = api_client.get(
            f"/reports/generations/{report.json()['id']}/artifact", headers=writer
        )
        assert artifact.status_code == 200, artifact.text
        download = api_client.get(
            f"/reports/generations/{report.json()['id']}/download", headers=writer
        )
        assert download.status_code == 200
        assert download.headers["x-content-sha256"] == artifact.json()["file_sha256"]
        assert (
            notes_instance["source_digest"] in download.content.decode("utf-8", errors="ignore")
            if report_format == "CSV"
            else True
        )
        if report_format == "CSV":
            assert "statement_line_id" in download.content.decode("utf-8")
            assert "account_id" in download.content.decode("utf-8")

    april = next(p for p in periods if p["period_no"] == 4)
    invalid_declaration = post_journal(
        api_client,
        owner,
        writer,
        {"accounting_period_id": april["id"], "entry_date": "2026-04-02", "source_type": "MANUAL"},
        [
            {"account_id": accounts["미처분이익잉여금"], "debit_amount": "4.0000"},
            {"account_id": accounts["현금및현금성자산"], "credit_amount": "4.0000"},
        ],
    )
    assert (
        api_client.post(
            "/equity/dividends",
            headers=writer,
            json={
                "resolution_date": "2026-04-02",
                "total_amount": "4.0000",
                "source_journal_id": invalid_declaration["id"],
            },
        ).status_code
        == 409
    )
    catalog = api_client.get("/reports/catalog", headers=owner).json()
    assert (
        next(item for item in catalog if item["code"] == "CHANGES_IN_EQUITY")["period_mode"]
        == "RANGE"
    )
    csv_run_id = None
    for format in ("CSV", "XLSX", "PDF"):
        report = api_client.post(
            "/reports/generations",
            headers={**writer, "Idempotency-Key": str(uuid4())},
            json={
                "report_code": "CHANGES_IN_EQUITY",
                "format": format,
                "period_id": february["id"],
                "period_preset": "CUSTOM",
                "date_from": february["start_date"],
                "date_to": february["end_date"],
            },
        )
        assert report.status_code == 201, report.text
        assert report.json()["status"] == "COMPLETED", report.text
        if format == "CSV":
            csv_run_id = report.json()["id"]
        assert report.json()["source_digest"] == generated.json()["snapshot_digest"]
        download = api_client.get(
            f"/reports/generations/{report.json()['id']}/download",
            headers=owner,
        )
        assert download.status_code == 200
        assert download.headers["X-Content-SHA256"] == sha256(download.content).hexdigest()
        if format == "CSV":
            content = download.content.decode("utf-8")
            assert "INTERNAL_VALIDATION_ONLY" in content
            assert equity_approval_id in content
            assert "CLOSING" in content and "225.0000" in content and "140.0000" in content
        elif format == "XLSX":
            book = load_workbook(BytesIO(download.content), read_only=True, data_only=True)
            assert book["Dataset"]["A1"].value == "movement_type"
            assert any(row[0] == "CLOSING" for row in book["Dataset"].iter_rows(values_only=True))
        else:
            assert download.content.startswith(b"%PDF-")
        assert api_client.get(
            f"/reports/generations/{report.json()['id']}/download",
            headers={**owner, "X-Company-ID": str(uuid4())},
        ).status_code in {403, 404}
    assert csv_run_id is not None
    history = api_client.get("/reports/generations", headers=owner)
    assert history.status_code == 200
    assert csv_run_id in {run["id"] for run in history.json()}
    assert (
        api_client.get(f"/reports/generations/{csv_run_id}/artifact", headers=owner).status_code
        == 200
    )
    policy = api_client.post(
        "/cash-flow/policies",
        headers=writer,
        json={
            "effective_from": "2026-03-01",
            "interest_paid": "OPERATING",
            "interest_received": "OPERATING",
            "income_tax_paid": "OPERATING",
        },
    )
    assert policy.status_code == 201, policy.text
    stale_choices = api_client.get(choices_url, headers=writer, params={"period_id": march["id"]})
    assert stale_choices.status_code == 200, stale_choices.text
    assert (
        next(
            row
            for row in stale_choices.json()["candidates"]
            if row["journal_id"] == excess_payment["id"]
        )["issue"]
        == "PAYMENT_SOURCE_STALE"
    )
    bridge = api_client.get(
        "/cash-flow/indirect-bridge", headers=writer, params={"period_id": march["id"]}
    )
    assert bridge.status_code == 200 and bridge.json()["status"] == "READY", bridge.text
    new_cash_flow = request(
        api_client,
        writer,
        "/cash-flow/generate",
        {
            key: bridge.json()[key]
            for key in (
                "period_id",
                "statement_set_id",
                "close_version",
                "source_digest",
                "mapping_digest",
            )
        },
    )
    assert new_cash_flow.status_code == 201 and new_cash_flow.json()["id"] != cash_flow.json()["id"]
    new_events = api_client.get(
        f"/cash-flow/{new_cash_flow.json()['id']}/drilldown", headers=writer
    ).json()["events"]
    duplicate_event = next(row for row in new_events if row["journal_id"] == first_payment["id"])
    assert duplicate_event["id"] != event_ids[first_payment["id"]]
    assert (
        api_client.post(
            payment_url, headers=writer, json={"cash_flow_event_id": duplicate_event["id"]}
        ).status_code
        == 409
    )
    new_choices = api_client.get(
        choices_url, headers=writer, params={"period_id": march["id"]}
    ).json()
    assert (
        next(row for row in new_choices["candidates"] if row["event_id"] == duplicate_event["id"])[
            "issue"
        ]
        == "PAYMENT_ALREADY_LINKED"
    )
    assert Decimal(new_choices["paid_amount"]) == Decimal("5")
    changed = api_client.post(
        "/equity/components",
        headers=writer,
        json={
            "component_code": "OTHER",
            "name": "기타자본",
            "component_type": "OTHER_EQUITY",
            "display_order": 3,
        },
    )
    assert changed.status_code == 201, changed.text
    stale = api_client.post(
        "/reports/generations",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={
            "report_code": "CHANGES_IN_EQUITY",
            "format": "CSV",
            "period_id": february["id"],
            "period_preset": "CUSTOM",
            "date_from": february["start_date"],
            "date_to": february["end_date"],
        },
    )
    assert stale.status_code == 409
    stale_review = api_client.get(review_path, headers=owner)
    assert stale_review.status_code == 200
    assert stale_review.json()["status"] == "APPROVED" and stale_review.json()["source_stale"]
    assert (
        api_client.get(f"/reports/generations/{csv_run_id}/download", headers=owner).status_code
        == 200
    )


def test_equity_stale_readiness_never_invents_amounts_or_changes_snapshots(
    api_client, auth_service
):
    from app.closing.infrastructure.models import ClosingRunModel
    from tests.integration.test_financial_statements import closed_company

    owner, writer, period_id, run_id, journal, connection = closed_company(api_client, auth_service)
    generated = request(
        api_client, writer, "/financial-statements/generate", {"period_id": period_id}
    )
    assert generated.status_code == 201, generated.text
    journal_before = api_client.get(f"/journals/{journal['id']}", headers=owner).json()
    statement_path = f"/financial-statements/sets/{generated.json()['id']}/INCOME_STATEMENT"
    statement_before = api_client.get(statement_path, headers=owner)
    assert statement_before.status_code == 200, statement_before.text
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        session.execute(
            update(ClosingRunModel)
            .where(ClosingRunModel.id == UUID(run_id))
            .values(adjusted_tb_digest="0" * 64)
        )
        session.commit()
    result = api_client.get(
        "/equity/reconciliation", headers=writer, params={"period_id": period_id}
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "BLOCKED"
    assert result.json()["issues"] == ["REPORT_SOURCE_STALE"]
    assert result.json()["balance_sheet_equity"] is None
    assert result.json()["income_statement_profit"] is None
    assert result.json()["rollforward_equity"] is None
    assert result.json()["source_rows"] == []
    attempt = request(api_client, writer, "/equity/statements/generate", {"period_id": period_id})
    assert attempt.status_code == 409 and attempt.json()["code"] == "REPORT_SOURCE_STALE"
    assert (
        api_client.get("/equity/statements", headers=writer, params={"period_id": period_id}).json()
        == []
    )
    assert api_client.get(f"/journals/{journal['id']}", headers=owner).json() == journal_before
    assert api_client.get(statement_path, headers=owner).json() == statement_before.json()
