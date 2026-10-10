"""복식부기와 상태전이는 LLM 없이 정확한 Decimal로 검증합니다."""

from decimal import Decimal
from uuid import uuid4
import pytest
from app.accounting.journals.domain.entities import JournalLine, validate_lines, totals, transition
from app.accounting.journals.domain.errors import AccountingError


def line(debit="0", credit="0", no=1):
    return JournalLine(
        id=uuid4(),
        line_no=no,
        account_id=uuid4(),
        debit_amount=Decimal(debit),
        credit_amount=Decimal(credit),
    )


def test_balanced_exact_decimal():
    lines = (line("0.1001"), line(credit="0.1001", no=2))
    validate_lines(lines)
    assert totals(lines) == (Decimal("0.1001"), Decimal("0.1001"))


@pytest.mark.parametrize("debit,credit", [("0", "0"), ("1", "1"), ("-1", "0"), ("0", "-1")])
def test_invalid_line_side(debit, credit):
    with pytest.raises(AccountingError):
        validate_lines((line(debit, credit), line("1", no=2)))


def test_imbalanced_draft_and_submit():
    lines = (line("2"), line(credit="1", no=2))
    validate_lines(lines, balanced=False)
    with pytest.raises(AccountingError, match="합계"):
        validate_lines(lines)


def test_posted_cannot_return_to_draft():
    with pytest.raises(AccountingError):
        transition("POSTED", "submit")
    assert transition("DRAFT", "submit") == "PROPOSED"
