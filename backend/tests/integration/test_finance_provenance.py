"""파일 증빙부터 거래·확정 전표·채권까지 관계형 출처를 추적합니다."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evidence.infrastructure.models import EvidenceModel
from tests.integration.test_finance_flow import finance_setup, post_journal, recognize
from tests.integration.test_intake_api import confirm, preview, upload


def test_finance_import_evidence_chain(api_client, auth_service):
    owner, writer, payload, accounts, cp, connection = finance_setup(api_client, auth_service)
    imported = upload(api_client, writer)
    draft = preview(api_client, writer, imported)
    response = confirm(api_client, writer, imported, draft)
    assert response.status_code == 200, response.text
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        evidence = session.scalar(
            select(EvidenceModel).where(
                EvidenceModel.company_id == UUID(writer["X-Company-ID"]),
                EvidenceModel.storage_object_id == UUID(imported["storage_object_id"]),
            )
        )
        assert evidence.sha256 == imported["file_sha256"]
        evidence_id = str(evidence.id)
    response = api_client.post(
        "/transactions",
        headers=writer,
        json={
            "transaction_date": "2026-01-02",
            "accounting_date": "2026-01-02",
            "description": "증빙 연결 매출",
            "amount": "100.0001",
            "direction": "INFLOW",
            "source_type": "SALES",
            "source_system": "IMPORT",
            "source_id": "source-1",
            "counterparty_id": cp,
            "import_id": imported["id"],
            "evidence_id": evidence_id,
        },
    )
    assert response.status_code == 201, response.text
    transaction = response.json()
    journal = post_journal(
        api_client,
        owner,
        writer,
        {
            **payload,
            "source_type": "TRANSACTION",
            "source_transaction_id": transaction["id"],
            "evidence_ids": [evidence_id],
        },
        [
            {"account_id": accounts["매출채권"], "counterparty_id": cp, "debit_amount": "100.0001"},
            {"account_id": accounts["매출"], "credit_amount": "100.0001"},
        ],
    )
    target = recognize(api_client, writer, journal, "AR")
    for result in (
        target,
        api_client.get(f"/receivables/{target['id']}?as_of=2026-01-31", headers=writer).json(),
        api_client.get("/receivables?as_of=2026-01-31", headers=writer).json()[0],
    ):
        assert result["source_transaction_id"] == transaction["id"]
        assert result["import_id"] == imported["id"]
        assert result["evidence_ids"] == [evidence_id]
    report = api_client.get("/receivables/reconciliation?as_of=2026-01-31", headers=writer).json()
    row = next(row for row in report["rows"] if row["account_name"] == "매출채권")
    assert row["evidence_ids"] == [evidence_id] and row["journal_ids"] == [journal["id"]]
