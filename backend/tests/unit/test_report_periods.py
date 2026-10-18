from datetime import UTC, date, datetime

import pytest

from app.contracts.access_errors import InvalidInput
from app.reporting.periods.rules import resolve


def period(preset, mode="RANGE", **kwargs):
    return resolve(
        preset,
        mode,
        timezone=kwargs.pop("timezone", "Asia/Seoul"),
        fiscal_year_start_month=kwargs.pop("fiscal_year_start_month", 4),
        week_start=kwargs.pop("week_start", 0),
        opening_date=kwargs.pop("opening_date", date(2020, 1, 1)),
        now=kwargs.pop("now", datetime(2026, 3, 1, 16, tzinfo=UTC)),
        **kwargs,
    )


def test_timezone_rollover_month_leap_year_and_fiscal_year():
    # UTC March 1 is March 2 in Seoul.
    assert period("TODAY").date_from == date(2026, 3, 2)
    assert period("THIS_MONTH").date_to == date(2026, 3, 31)
    year = period("THIS_YEAR")
    assert (year.date_from, year.date_to) == (date(2025, 4, 1), date(2026, 3, 31))
    leap = period("THIS_MONTH", now=datetime(2024, 2, 10, tzinfo=UTC))
    assert leap.date_to == date(2024, 2, 29)


def test_week_start_policy_and_as_of_semantics():
    monday = period("THIS_WEEK")
    sunday = period("THIS_WEEK", week_start=6)
    assert (monday.date_from, monday.date_to) == (date(2026, 3, 2), date(2026, 3, 8))
    assert (sunday.date_from, sunday.date_to) == (date(2026, 3, 1), date(2026, 3, 7))
    assert period("THIS_YEAR", "AS_OF").as_of == date(2026, 3, 2)


def test_custom_range_and_opening_date_policy():
    value = period("CUSTOM", date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    assert (value.date_from, value.date_to) == (date(2026, 1, 1), date(2026, 1, 31))
    partial = period("THIS_YEAR", opening_date=date(2025, 8, 1))
    assert partial.date_from == date(2025, 8, 1) and partial.partial
    with pytest.raises(InvalidInput):
        period("CUSTOM", date_from=date(2019, 12, 31), date_to=date(2020, 1, 1))
    with pytest.raises(InvalidInput):
        period("CUSTOM", date_from=date(2026, 2, 1), date_to=date(2026, 1, 1))
    with pytest.raises(InvalidInput):
        period("CUSTOM", "AS_OF", as_of=date(2019, 12, 31))
    with pytest.raises(InvalidInput):
        period("CUSTOM", "AS_OF", as_of=date(2026, 4, 1))
    with pytest.raises(InvalidInput):
        period("THIS_MONTH", date_from=date(2026, 3, 1))
