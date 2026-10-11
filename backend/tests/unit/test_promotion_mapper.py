from dataclasses import replace
from decimal import Decimal

import pytest

from app.contracts.access_errors import InvalidInput, StateConflict
from app.intake.domain.canonical_fields import SourceType
from app.intake.domain.validation import CanonicalRow
from app.intake.promotion.domain.mapper import map_row


def row(**values):
    return CanonicalRow(
        0,
        2,
        "s-1",
        tuple(
            {
                "transaction_date": "2025-01-02",
                "amount": "11000.0001",
                "currency": "KRW",
                **values,
            }.items()
        ),
    )


def test_mapper_exact_decimal_and_identity():
    fact = map_row(SourceType.SALES, row(tax_amount="1000.0001"))
    assert fact.amount == Decimal("11000.0001") and fact.tax_amount == Decimal("1000.0001")
    assert fact.direction == "INFLOW" and fact.accounting_date == fact.transaction_date
    assert (
        fact.fingerprint
        == map_row(
            SourceType.SALES, replace(row(tax_amount="1000.0001"), sheet_index=1, row_number=9)
        ).fingerprint
    )
    assert (
        fact.fingerprint
        != map_row(SourceType.SALES, row(amount="12000", tax_amount="1000.0001")).fingerprint
    )


@pytest.mark.parametrize(
    "values",
    [
        dict(amount="-1"),
        dict(amount="0"),
        dict(amount="NaN"),
        dict(amount="1e100"),
        dict(amount="1.00001"),
        dict(currency="USD"),
        dict(tax_amount="12000"),
        dict(tax_amount="-1"),
        dict(direction="INVALID"),
        dict(payment_method="OTHER"),
        dict(transaction_date="bad"),
    ],
)
def test_mapper_rejects_unsupported_facts(values):
    with pytest.raises(InvalidInput):
        map_row(SourceType.SALES, row(**values))


def test_bank_direction_and_opening_boundary():
    with pytest.raises(InvalidInput):
        map_row(SourceType.BANK_TRANSACTION, row())
    with pytest.raises(StateConflict):
        map_row(SourceType.OPENING_BALANCE, row())
    assert map_row(SourceType.PURCHASE, row()).direction == "OUTFLOW"
