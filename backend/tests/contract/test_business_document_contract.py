"""업무문서 API의 명령·회사·재시도·입력 경계를 검증합니다."""

import pytest
from pydantic import ValidationError

from app.accounting.transactions.api.schemas import TransactionCreate
from app.finance.invoices.api.schemas import InvoiceCreate, LineInput, NoteCreate, VersionCommand
from app.main import create_app


def test_document_openapi_commands_require_company_and_idempotency(settings):
    paths = create_app(settings).openapi()["paths"]
    for prefix in ("sales-invoices", "purchase-invoices", "credit-notes", "debit-notes"):
        assert "get" in paths["/" + prefix]
        assert "get" in paths["/" + prefix + "/{resource_id}"]
        for path in (
            "/" + prefix,
            "/" + prefix + "/{resource_id}/submit",
            "/" + prefix + "/{resource_id}/approve",
        ):
            operation = paths[path]["post"]
            for header in ("X-Company-ID", "Idempotency-Key"):
                assert any(p["name"] == header and p["required"] for p in operation["parameters"])
    for model in (InvoiceCreate, LineInput, NoteCreate, VersionCommand):
        assert model.model_config["extra"] == "forbid"


@pytest.mark.parametrize("amount", [1.1, True, "NaN", "-1", "1.00001"])
def test_document_money_rejects_lossy_or_invalid_values(amount):
    with pytest.raises(ValidationError):
        LineInput(line_no=1, description="검증 항목", supply_amount=amount, tax_amount="0")


def test_document_commands_cannot_inject_status_or_company():
    with pytest.raises(ValidationError):
        VersionCommand(expected_version=1, status="APPROVED")
    with pytest.raises(ValidationError):
        VersionCommand(expected_version=1, company_id="forged")
    with pytest.raises(ValidationError):
        TransactionCreate.model_validate(
            {
                "transaction_date": "2026-01-02",
                "accounting_date": "2026-01-02",
                "description": "위조 출처",
                "amount": "100",
                "direction": "INFLOW",
                "source_id": "forged",
                "source_type": "BUSINESS_DOCUMENT",
            }
        )
