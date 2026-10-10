from decimal import Decimal

import pytest

from app.onboarding.domain.catalog import BY_CODE, CATALOG
from app.onboarding.domain.errors import InvalidValue
from app.onboarding.domain.validation import invalidate, progress, recalculate, validate
from app.onboarding.domain.values import Cell, classify, parse_value, required, row_key


def test_catalog_and_conditional_required() -> None:
    assert len(BY_CODE) == len(CATALOG)
    field = BY_CODE["Company.corporation_number"]
    assert not required(field, [])
    assert required(field, [Cell("Company.taxpayer_type", "singleton", "CORPORATION")])


@pytest.mark.parametrize("value", [1.2, True, "NaN", "1.00001", "1e999"])
def test_decimal_rejects_unsafe_values(value: object) -> None:
    with pytest.raises((InvalidValue, ValueError)):
        parse_value(BY_CODE["Opening_Balances.debit_amount"], value)


def test_decimal_and_stable_merge_key() -> None:
    assert parse_value(BY_CODE["Opening_Balances.debit_amount"], "12.50") == Decimal("12.50")
    assert row_key("COA", {"account_code": "101"}) == "101"
    incoming = Cell("COA.account_name", "101", "현금")
    assert classify(None, incoming) == "APPLY"
    assert classify(incoming, incoming) == "UNCHANGED"
    assert classify(Cell("COA.account_name", "101", "예금"), incoming) == "CONFLICT"


def test_derived_invalidation_and_progress_exclusion() -> None:
    cells = recalculate([Cell("Opening_Balances.debit_amount", "2025|101|", Decimal("10.25"))])
    assert next(c.value for c in cells if c.field_code.endswith("debit_total")) == Decimal("10.25")
    stale = invalidate(cells, {"Opening_Balances"})
    assert all(c.status == "STALE" for c in stale if c.source_type == "DERIVED")
    assert progress(cells, "Opening_Balances")[1] == 6
    assert any(i.validation_code == "PENDING_DOMAIN_SUPPORT" for i in validate(cells))
