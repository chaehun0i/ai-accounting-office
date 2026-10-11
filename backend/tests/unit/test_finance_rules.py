from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.accounting.journals.domain.errors import AccountingError
from app.finance.settlements.domain.rules import (
    aging_bucket,
    check_version,
    outstanding,
    positive,
    target_status,
)


@pytest.mark.parametrize("paid,status", [("0", "OPEN"), ("5.5", "PARTIAL"), ("11", "SETTLED")])
def test_settlement_status(paid: str, status: str) -> None:
    assert target_status(Decimal("11"), Decimal(paid)) == status
    assert outstanding(Decimal("11"), Decimal(paid)) == Decimal("11") - Decimal(paid)


@pytest.mark.parametrize(
    "days,bucket",
    [
        (-1, "CURRENT"),
        (0, "CURRENT"),
        (1, "1-30"),
        (30, "1-30"),
        (31, "31-60"),
        (60, "31-60"),
        (61, "61-90"),
        (90, "61-90"),
        (91, "90+"),
    ],
)
def test_aging(days: int, bucket: str) -> None:
    today = date(2026, 10, 11)
    assert aging_bucket(today - timedelta(days=days), today) == bucket


def test_excess_and_stale() -> None:
    with pytest.raises(AccountingError, match="배분"):
        outstanding(Decimal("1"), Decimal("1.0001"))
    with pytest.raises(AccountingError) as error:
        check_version(2, 1)
    assert error.value.code == "SETTLEMENT_TARGET_STALE"
    with pytest.raises((TypeError, ValueError)):
        positive(1.5)  # type: ignore[arg-type]
