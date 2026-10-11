from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.accounting.dimensions.domain.entities import Dimension, DimensionValue
from app.accounting.dimensions.domain.rules import (
    validate_dates,
    validate_definition,
    validate_policy,
    validate_selection,
)
from app.accounting.journals.domain.errors import AccountingError
from app.contracts.access_errors import InvalidInput


@pytest.fixture
def axis():
    now = datetime.now(UTC)
    dimension = Dimension(
        id=uuid4(),
        company_id=uuid4(),
        dimension_code="DEPT",
        name="부서",
        dimension_type="DEPARTMENT",
        status="ACTIVE",
        required_policy="OPTIONAL",
        version=1,
        created_at=now,
        updated_at=now,
    )
    value = DimensionValue(
        id=uuid4(),
        company_id=dimension.company_id,
        dimension_id=dimension.id,
        value_code="SALES",
        name="영업",
        parent_value_id=None,
        status="ACTIVE",
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 12, 31),
        version=1,
        created_at=now,
        updated_at=now,
    )
    return dimension, value


@pytest.mark.parametrize(
    "code,name,status",
    [
        ("bad code", "부서", "ACTIVE"),
        ("", "부서", "ACTIVE"),
        ("D", " ", "ACTIVE"),
        ("D", "부서", "UNKNOWN"),
    ],
)
def test_invalid_definitions(code, name, status):
    with pytest.raises(InvalidInput):
        validate_definition(code, name, status)


def test_effective_dates():
    with pytest.raises(InvalidInput):
        validate_dates(date(2025, 2, 1), date(2025, 1, 1))


def test_optional_and_required(axis):
    d, v = axis
    validate_selection(d.company_id, date(2025, 1, 1), (), [d], [v])
    with pytest.raises(AccountingError, match="필수"):
        validate_selection(
            d.company_id, date(2025, 1, 1), (), [replace(d, required_policy="REQUIRED")], [v]
        )
    validate_selection(
        d.company_id, date(2025, 1, 1), (v.id,), [replace(d, required_policy="REQUIRED")], [v]
    )


@pytest.mark.parametrize(
    "change", ["inactive_value", "inactive_dimension", "expired", "future", "foreign", "missing"]
)
def test_invalid_selection(axis, change):
    d, v = axis
    if change == "inactive_value":
        v = replace(v, status="INACTIVE")
    if change == "inactive_dimension":
        d = replace(d, status="INACTIVE")
    if change == "expired":
        v = replace(v, effective_to=date(2025, 1, 1))
    if change == "future":
        v = replace(v, effective_from=date(2025, 12, 1))
    if change == "foreign":
        v = replace(v, company_id=uuid4())
    with pytest.raises(AccountingError) as caught:
        validate_selection(
            d.company_id, date(2025, 6, 1), (uuid4() if change == "missing" else v.id,), [d], [v]
        )
    assert caught.value.code == "DIMENSION_VALUE_INVALID"


def test_same_type_duplicate_even_different_dimension(axis):
    d, v = axis
    second = replace(d, id=uuid4(), dimension_code="OTHER_DEPT")
    other = replace(v, id=uuid4(), dimension_id=second.id)
    with pytest.raises(AccountingError) as caught:
        validate_selection(
            d.company_id, date(2025, 6, 1), (v.id, other.id), [d, second], [v, other]
        )
    assert caught.value.code == "DIMENSION_DUPLICATE_TYPE"


def test_valid_effective_boundaries_and_four_types(axis):
    d, v = axis
    for kind in ("BUSINESS_UNIT", "DEPARTMENT", "PROJECT", "COST_CENTER"):
        for day in (v.effective_from, v.effective_to):
            validate_selection(d.company_id, day, (v.id,), [replace(d, dimension_type=kind)], [v])


@pytest.mark.parametrize("kind,policy", [("UNKNOWN", "OPTIONAL"), ("DEPARTMENT", "UNKNOWN")])
def test_invalid_type_and_policy(kind, policy):
    with pytest.raises(InvalidInput):
        validate_policy([], kind, "ACTIVE", policy)


def test_same_type_required_configuration(axis):
    d, _ = axis
    required = replace(d, required_policy="REQUIRED")
    with pytest.raises(AccountingError):
        validate_policy([required], d.dimension_type, "ACTIVE", "REQUIRED")
    validate_policy([required], d.dimension_type, "ACTIVE", "REQUIRED", d.id)
    validate_policy([required], d.dimension_type, "INACTIVE", "REQUIRED")
