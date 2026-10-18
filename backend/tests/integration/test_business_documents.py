"""문서 승인부터 거래·보조부 연결 및 재시도를 실제 PostgreSQL에서 검증합니다."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from tests.integration.test_finance_allocations import confirm, make_record
from tests.integration.test_finance_flow import allocate, finance_setup, post_journal


def body(counterparty, number="S-001", supply="10000000", tax="1000000"):
    return {
        "document_no": number,
        "counterparty_id": counterparty,
        "issue_date": "2026-01-02",
        "accounting_date": "2026-01-02",
        "due_date": "2026-01-20",
        "source_id": number,
        "lines": [
            {"line_no": 1, "description": "용역 공급", "supply_amount": supply, "tax_amount": tax}
        ],
    }


def create(client, writer, path, payload):
    result = client.post(path, headers={**writer, "Idempotency-Key": str(uuid4())}, json=payload)
    assert result.status_code == 201, result.text
    return result.json()


def transition(client, actor, path, value, action, key=None, version=None):
    return client.post(
        f"{path}/{value['id']}/{action}",
        headers={**actor, "Idempotency-Key": key or str(uuid4())},
        json={"expected_version": version or value["version"]},
    )


@pytest.mark.parametrize(
    "path,obligations,amount,supply,tax",
    [
        ("/sales-invoices", "/receivables", "11000000.0000", "10000000", "1000000"),
        ("/purchase-invoices", "/payables", "3300000.0000", "3000000", "300000"),
    ],
)
def test_document_approval_creates_transaction_and_obligation(
    api_client, auth_service, path, obligations, amount, supply, tax
):
    owner, writer, _, _, cp, _ = finance_setup(api_client, auth_service)
    value = create(api_client, writer, path, body(cp, supply=supply, tax=tax))
    assert value["transaction_id"] is None
    submitted = transition(api_client, writer, path, value, "submit")
    assert submitted.status_code == 200, submitted.text
    value = submitted.json()
    assert transition(api_client, writer, path, value, "approve").status_code == 403
    key = str(uuid4())
    approved = transition(api_client, owner, path, value, "approve", key)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["transaction_id"]
    transaction = api_client.get(
        "/transactions/" + approved.json()["transaction_id"], headers=writer
    )
    assert transaction.status_code == 200, transaction.text
    assert transaction.json()["source_type"] == "BUSINESS_DOCUMENT"
    assert transaction.json()["amount"] == amount
    assert transition(api_client, owner, path, value, "approve", key).json() == approved.json()
    assert transition(api_client, owner, path, value, "approve", key, 999).status_code == 409
    rows = api_client.get(obligations + "?as_of=2026-12-31", headers=writer).json()
    assert len(rows) == 1, rows
    assert rows[0]["original_amount"] == amount
    assert rows[0]["outstanding_amount"] == amount
    assert rows[0]["origin_journal_id"] is None
    assert rows[0]["source_invoice_id"] == value["id"]
    assert api_client.get(path + "/" + value["id"], headers=writer).json() == approved.json()


def test_credit_note_preserves_original_and_adjusts_outstanding(api_client, auth_service):
    owner, writer, _, _, cp, _ = finance_setup(api_client, auth_service)
    value = create(api_client, writer, "/sales-invoices", body(cp))
    replay_key = str(uuid4())
    reused = api_client.post(
        "/sales-invoices", headers={**writer, "Idempotency-Key": replay_key}, json=body(cp)
    )
    assert reused.status_code == 201 and reused.json()["id"] == value["id"]
    changed = api_client.post(
        "/sales-invoices",
        headers={**writer, "Idempotency-Key": replay_key},
        json=body(cp, supply="999"),
    )
    assert changed.status_code == 409 and changed.json()["code"] == "IDEMPOTENCY_CONFLICT"
    value = transition(api_client, writer, "/sales-invoices", value, "submit").json()
    value = transition(api_client, owner, "/sales-invoices", value, "approve").json()
    note = create(
        api_client,
        writer,
        "/credit-notes",
        {
            **body(cp, "CN-001", "2000000", "200000"),
            "original_document_type": "SALES_INVOICE",
            "original_document_id": value["id"],
            "reason_code": "RETURN",
            "expected_version": value["version"],
        },
    )
    note = transition(api_client, writer, "/credit-notes", note, "submit").json()
    result = transition(api_client, owner, "/credit-notes", note, "approve")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "APPLIED"
    assert api_client.get("/sales-invoices/" + value["id"], headers=writer).json() == value
    rows = api_client.get("/receivables?as_of=2026-12-31", headers=writer).json()
    assert rows[0]["original_amount"] == "11000000.0000"
    assert rows[0]["outstanding_amount"] == "8800000.0000"


def approved_invoice(client, owner, writer, cp):
    value = create(client, writer, "/sales-invoices", body(cp))
    value = transition(client, writer, "/sales-invoices", value, "submit").json()
    result = transition(client, owner, "/sales-invoices", value, "approve")
    assert result.status_code == 200, result.text
    return result.json()


def note_payload(cp, original, number="CN-001", supply="2000000", tax="200000"):
    return {
        **body(cp, number, supply, tax),
        "original_document_type": "SALES_INVOICE",
        "original_document_id": original["id"],
        "reason_code": "RETURN",
        "expected_version": original["version"],
    }


def test_partial_settlement_credit_debit_and_gl_link(api_client, auth_service):
    api_client.raise_server_exceptions = True
    owner, writer, payload, accounts, cp, _ = finance_setup(api_client, auth_service)
    value = approved_invoice(api_client, owner, writer, cp)
    journal = post_journal(
        api_client,
        owner,
        writer,
        {**payload, "source_type": "TRANSACTION", "source_transaction_id": value["transaction_id"]},
        [
            {
                "account_id": accounts["외상매출금"],
                "counterparty_id": cp,
                "debit_amount": "11000000",
            },
            {"account_id": accounts["매출"], "credit_amount": "11000000"},
        ],
    )
    result = api_client.post(
        "/receivables/from-journals",
        headers=writer,
        json={"journal_id": journal["id"], "due_date": "2026-01-20"},
    )
    assert result.status_code == 200, result.text
    target = result.json()[0]
    assert target["id"] == value["obligation_id"]
    accounting = {**accounts, "매출채권": accounts["외상매출금"]}
    path, record = make_record(
        api_client, owner, writer, payload, accounting, cp, "AR", Decimal("5500000")
    )
    record = allocate(api_client, writer, path, record, [(target, Decimal("5500000"))])
    assert confirm(api_client, writer, path, record).status_code == 200
    for path, number in [("/credit-notes", "CN-001"), ("/debit-notes", "DN-001")]:
        note = create(api_client, writer, path, note_payload(cp, value, number))
        note = transition(api_client, writer, path, note, "submit").json()
        applied = transition(api_client, owner, path, note, "approve")
        assert applied.status_code == 200, applied.text
        remaining = api_client.get("/receivables?as_of=2026-12-31", headers=writer).json()
        assert len(remaining) == 1
        assert remaining[0]["outstanding_amount"] == (
            "3300000.0000" if path == "/credit-notes" else "5500000.0000"
        )


def test_rollback_retry_and_immutable_document(api_client, auth_service, monkeypatch):
    from sqlalchemy import select, update
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from app.finance.invoices.infrastructure.models import SalesInvoiceModel
    from app.finance.receivables.application.service import ObligationService

    owner, writer, _, _, cp, connection = finance_setup(api_client, auth_service)
    value = create(api_client, writer, "/sales-invoices", body(cp))
    value = transition(api_client, writer, "/sales-invoices", value, "submit").json()
    original = ObligationService.recognize_invoice_in

    def fail(*args, **kwargs):
        raise RuntimeError("테스트 강제 실패")

    monkeypatch.setattr(ObligationService, "recognize_invoice_in", staticmethod(fail))
    key = str(uuid4())
    assert (
        transition(api_client, owner, "/sales-invoices", value, "approve", key).status_code == 500
    )
    assert (
        api_client.get("/sales-invoices/" + value["id"], headers=writer).json()["transaction_id"]
        is None
    )
    monkeypatch.setattr(ObligationService, "recognize_invoice_in", staticmethod(original))
    result = transition(api_client, owner, "/sales-invoices", value, "approve", key)
    assert result.status_code == 200, result.text
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        with pytest.raises(IntegrityError):
            session.execute(
                update(SalesInvoiceModel)
                .where(SalesInvoiceModel.id == UUID(result.json()["id"]))
                .values(total_amount=Decimal("1"))
            )
        session.rollback()
        assert session.scalar(select(SalesInvoiceModel.total_amount)) == Decimal("11000000")


def test_document_security_stale_and_source_conflict(api_client, auth_service):
    from sqlalchemy import update

    from app.companies.infrastructure.models import MembershipModel
    from tests.integration.test_intake_api import COMPANY

    owner, writer, _, _, cp, connection = finance_setup(api_client, auth_service)
    value = create(api_client, writer, "/sales-invoices", body(cp))
    assert (
        transition(api_client, writer, "/sales-invoices", value, "submit", version=999).status_code
        == 409
    )
    collision = api_client.post(
        "/sales-invoices",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json=body(cp, supply="999"),
    )
    assert collision.json()["code"] == "IMPORT_SOURCE_CONFLICT"
    assert (
        api_client.post(
            "/sales-invoices",
            headers={**writer, "X-CSRF-Protection": "0", "Idempotency-Key": str(uuid4())},
            json=body(cp, "csrf"),
        ).status_code
        == 403
    )
    other = api_client.post(
        "/companies",
        headers=owner,
        json={**COMPANY, "business_number": "9876543210", "company_name": "다른 회사"},
    ).json()
    assert (
        api_client.get(
            "/sales-invoices/" + value["id"], headers={**owner, "X-Company-ID": other["id"]}
        ).status_code
        == 404
    )
    owner_actor = api_client.app.state.services.auth.authenticate(
        owner["Authorization"].removeprefix("Bearer ")
    )
    connection.execute(
        update(MembershipModel)
        .where(
            MembershipModel.company_id == UUID(owner["X-Company-ID"]),
            MembershipModel.user_id == owner_actor.user_id,
        )
        .values(role_code="VIEWER")
    )
    assert (
        api_client.post(
            "/sales-invoices",
            headers={**owner, "Idempotency-Key": str(uuid4())},
            json=body(cp, "forbidden"),
        ).status_code
        == 403
    )


def test_inactive_counterparty_and_self_approval_fail_closed(api_client, auth_service):
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.companies.infrastructure.models import MembershipModel
    from app.master_data.counterparties.infrastructure.models import CounterpartyModel

    owner, writer, _, _, cp, connection = finance_setup(api_client, auth_service)
    value = create(api_client, writer, "/sales-invoices", body(cp))
    submitted = transition(api_client, writer, "/sales-invoices", value, "submit").json()
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        session.execute(
            update(CounterpartyModel)
            .where(CounterpartyModel.id == UUID(cp))
            .values(status="INACTIVE")
        )
        session.commit()
    denied = transition(api_client, owner, "/sales-invoices", submitted, "approve")
    assert denied.status_code == 404
    assert (
        api_client.get("/sales-invoices/" + value["id"], headers=writer).json()["transaction_id"]
        is None
    )
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        session.execute(
            update(CounterpartyModel)
            .where(CounterpartyModel.id == UUID(cp))
            .values(status="ACTIVE")
        )
        session.execute(
            update(MembershipModel)
            .where(
                MembershipModel.company_id == UUID(writer["X-Company-ID"]),
                MembershipModel.role_code == "ACCOUNTANT",
            )
            .values(role_code="OWNER")
        )
        session.commit()
    denied = transition(api_client, writer, "/sales-invoices", submitted, "approve")
    assert denied.status_code == 409
    assert denied.json()["code"] == "SELF_APPROVAL_NOT_ALLOWED"
