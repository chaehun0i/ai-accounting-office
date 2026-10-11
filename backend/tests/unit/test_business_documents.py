"""업무문서 원천의 금액과 정정 관계를 검증합니다."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.accounting.journals.domain.errors import AccountingError
from app.contracts.access_errors import InvalidInput, StateConflict
from app.finance.invoices.domain.entities import (
    Document,
    DocumentLine,
    DocumentStatus,
    DocumentType,
)
from app.finance.invoices.domain.rules import (
    document_fingerprint,
    require_transition,
    validate_document,
)


def invoice(**changes: object) -> Document:
    value = Document(
        id=uuid4(),
        company_id=uuid4(),
        document_type=DocumentType.SALES_INVOICE,
        document_no="S-001",
        counterparty_id=uuid4(),
        issue_date=date(2025, 1, 2),
        accounting_date=date(2025, 1, 2),
        due_date=date(2025, 2, 2),
        currency_code="KRW",
        source_system="MANUAL",
        source_id="S-001",
        source_fingerprint="",
        status=DocumentStatus.DRAFT,
        version=1,
        created_by=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        lines=(
            DocumentLine(
                line_no=1,
                description="용역",
                supply_amount=Decimal("10000000"),
                tax_amount=Decimal("1000000"),
            ),
        ),
    )
    return replace(value, **changes)


def test_golden_source_amounts() -> None:
    value = invoice()
    validate_document(value)
    assert value.total_amount == Decimal("11000000")
    assert value.tax_amount == Decimal("1000000")
    assert value.kind == "AR"
    assert replace(value, document_type=DocumentType.PURCHASE_INVOICE).kind == "AP"


@pytest.mark.parametrize("amount", ["-1", "NaN", "Infinity", "0.00001", "1000000000000000"])
def test_invalid_amount(amount: str) -> None:
    line = replace(invoice().lines[0], supply_amount=Decimal(amount))
    with pytest.raises(AccountingError):
        validate_document(invoice(lines=(line,)))


def test_precision_stable_fingerprint() -> None:
    value = invoice()
    same = replace(value, lines=(replace(value.lines[0], supply_amount=Decimal("10000000.0000")),))
    assert document_fingerprint(value) == document_fingerprint(same)
    assert document_fingerprint(value) != document_fingerprint(
        replace(value, due_date=date(2025, 3, 2))
    )
    assert document_fingerprint(value) == document_fingerprint(replace(value, version=2))


def test_quantity_is_source_fact_not_rounding_guess() -> None:
    value = invoice()
    line = replace(value.lines[0], quantity=Decimal("2"), unit_price=Decimal("5000000"))
    validate_document(replace(value, lines=(line,)))
    with pytest.raises(AccountingError):
        validate_document(replace(value, lines=(replace(line, quantity=Decimal("3")),)))
    with pytest.raises(InvalidInput):
        validate_document(replace(value, lines=(replace(line, unit_price=None),)))


def test_notes_require_explicit_original_and_reason() -> None:
    value = invoice(document_type=DocumentType.CREDIT_NOTE)
    with pytest.raises(InvalidInput):
        validate_document(value)
    value = replace(
        value,
        original_document_type=DocumentType.SALES_INVOICE,
        original_document_id=uuid4(),
        reason_code="RETURN",
    )
    validate_document(value)
    assert value.kind == "AR"
    with pytest.raises(InvalidInput):
        validate_document(replace(value, original_document_id=value.id))


def test_only_explicit_transition_commands() -> None:
    value = invoice()
    assert require_transition(value, "submit") == DocumentStatus.REVIEW_REQUIRED
    with pytest.raises(StateConflict):
        require_transition(value, "approve")
    value = replace(value, status=DocumentStatus.REVIEW_REQUIRED)
    assert require_transition(value, "approve") == DocumentStatus.APPROVED
    assert (
        require_transition(replace(value, document_type=DocumentType.CREDIT_NOTE), "approve")
        == DocumentStatus.APPLIED
    )
    with pytest.raises(StateConflict):
        require_transition(replace(value, status=DocumentStatus.APPROVED), "submit")
