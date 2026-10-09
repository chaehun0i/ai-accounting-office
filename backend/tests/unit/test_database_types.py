from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.dialects.postgresql import dialect

from app.core.database.types import MoneyNumeric, ResourceUUID, UTCDateTime
from app.core.values import as_utc, new_uuid, require_money, require_uuid


def test_postgresql_type_contract() -> None:
    assert str(ResourceUUID().compile(dialect=dialect())) == "UUID"
    assert str(MoneyNumeric().compile(dialect=dialect())) == "NUMERIC(19, 4)"
    assert str(UTCDateTime().compile(dialect=dialect())) == "TIMESTAMP WITH TIME ZONE"
    assert MoneyNumeric().impl.asdecimal is True


@pytest.mark.parametrize(
    "value",
    [
        0.1,
        1,
        "1.00",
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("1000000000000000"),
        Decimal("-1000000000000000"),
        Decimal("0.00001"),
    ],
)
def test_money_rejects_implicit_conversion_or_rounding(value: object) -> None:
    with pytest.raises(ValueError):
        require_money(value)


def test_exact_money_and_uuid() -> None:
    value = Decimal("999999999999999.9999")
    assert require_money(value) is value
    assert require_money(Decimal("1.00000")) == Decimal("1")
    identity = new_uuid()
    assert isinstance(identity, UUID)
    assert identity.version == 4
    assert require_uuid(identity) is identity
    with pytest.raises(ValueError):
        require_uuid(str(identity))


def test_timezone_boundary() -> None:
    source = datetime(2026, 10, 9, 22, 0, tzinfo=timezone(timedelta(hours=9)))
    assert as_utc(source) == datetime(2026, 10, 9, 13, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        as_utc(datetime(2026, 10, 9))
