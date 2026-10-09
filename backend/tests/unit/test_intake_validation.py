from decimal import Decimal

import pytest

from app.intake.domain.canonical_fields import SourceType, suggest
from app.intake.domain.digest import digest
from app.intake.domain.validation import validate, value_for
from app.intake.infrastructure.parser import parse_file


def test_validation_keeps_decimal_and_source_identity() -> None:
    book = parse_file(
        "data.csv", b"source_id,date,amount,currency\ns1,2026-01-01,10.0001,KRW", "text/csv"
    )
    records, errors = validate(
        book, SourceType.SALES, suggest(SourceType.SALES, 0, book.sheets[0].headers)
    )
    assert not errors
    assert dict(records[0].values)["amount"] == "10.0001"
    assert digest({"b": 2, "a": 1}) == digest({"a": 1, "b": 2})
    assert Decimal(value_for("decimal", "10.0001")) == Decimal("10.0001")


@pytest.mark.parametrize(
    "kind,value",
    [
        ("date", "2026-02-30"),
        ("decimal", "nan"),
        ("decimal", "1.00001"),
        ("currency", "XXX"),
        ("direction", "INVALID"),
    ],
)
def test_invalid_values_are_rejected(kind: str, value: str) -> None:
    with pytest.raises(ValueError):
        value_for(kind, value)
