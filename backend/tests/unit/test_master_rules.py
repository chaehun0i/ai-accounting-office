from datetime import date

import pytest

from app.accounting.domain.rules import (
    journal_number,
    monthly_periods,
    validate_account,
    validate_hierarchy,
)
from app.contracts.access_errors import InvalidInput
from app.master_data.domain.rules import DueRule, due_date, normalized_identifier, normalized_name


def test_payment_due_rules_and_contract_override() -> None:
    base = date(2026, 2, 5)
    assert due_date(base, DueRule.NET_DAYS, 30) == date(2026, 3, 7)
    assert due_date(base, DueRule.MONTH_END_PLUS_DAYS, 10) == date(2026, 3, 10)
    assert due_date(base, DueRule.IMMEDIATE, 0) == base
    assert due_date(base, DueRule.NET_DAYS, 30, base) == base
    with pytest.raises(InvalidInput):
        due_date(base, DueRule.IMMEDIATE, 1)


def test_identifier_and_name_normalization() -> None:
    assert normalized_identifier("123-45-67890", 10) == "1234567890"
    assert normalized_identifier("  ", 10) is None
    assert normalized_name("  CUSTOMER   A ") == "customer a"
    with pytest.raises(InvalidInput):
        normalized_identifier("not-a-number", 10)


@pytest.mark.parametrize("month", [1, 4, 7, 12])
def test_fiscal_periods_are_contiguous(month: int) -> None:
    periods = monthly_periods(2024, month)
    assert len(periods) == 12
    assert periods[0][1] == date(2024, month, 1)
    assert periods[-1][2].year == (2024 if month == 1 else 2025)
    assert all(
        (right[1] - left[2]).days == 1 for left, right in zip(periods, periods[1:], strict=False)
    )
    if month == 1:
        assert periods[1][2] == date(2024, 2, 29)


def test_account_contra_policy_and_hierarchy() -> None:
    validate_account("ASSET", "DEBIT")
    validate_account("ASSET", "CREDIT", True)
    with pytest.raises(InvalidInput):
        validate_account("ASSET", "CREDIT")
    with pytest.raises(InvalidInput):
        validate_account("UNKNOWN", "CREDIT")
    validate_hierarchy({"1": None, "11": "1"})
    for parents in ({"1": "2", "2": "1"}, {"1": "missing"}):
        with pytest.raises(InvalidInput):
            validate_hierarchy(parents)
    assert journal_number("J", 2026, 1) == "J-2026-000001"
