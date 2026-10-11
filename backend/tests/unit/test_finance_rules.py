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


def test_due_windows_and_settled_exclusion() -> None:
    from uuid import uuid4

    from app.finance.receivables.domain.entities import Obligation
    from app.finance.reconciliation.domain.reports import aging

    today = date(2026, 10, 11)
    cp = uuid4()
    values = [
        Obligation(
            id=uuid4(),
            company_id=uuid4(),
            counterparty_id=cp,
            counterparty_name="거래처",
            origin_journal_id=uuid4(),
            origin_line_no=1,
            account_id=uuid4(),
            original_amount=Decimal("10"),
            outstanding_amount=Decimal("0" if days == 90 else "10"),
            currency_code="KRW",
            due_date=today + timedelta(days=days),
            status="OPEN",
            version=1,
            origin_date=today - timedelta(days=100),
        )
        for days in (-1, 0, 7, 8, 30, 31, 90)
    ]
    result = aging(values, today)
    assert result.total_outstanding == 60
    assert result.overdue == 10
    assert result.due_7d == 20
    assert result.due_30d == 40
    assert result.counterparties[cp] == 60
