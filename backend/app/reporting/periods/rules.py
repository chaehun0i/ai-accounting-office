"""Resolve report presets using a company's timezone and fiscal policy."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.contracts.access_errors import InvalidInput

Preset = Literal["TODAY", "THIS_WEEK", "THIS_MONTH", "THIS_YEAR", "CUSTOM"]
Semantics = Literal["RANGE", "AS_OF"]


@dataclass(frozen=True)
class ResolvedPeriod:
    period_preset: Preset
    period_mode: Semantics
    timezone: str
    date_from: date | None
    date_to: date | None
    as_of: date | None
    partial: bool = False


def resolve(
    preset: Preset,
    mode: Semantics,
    *,
    timezone: str,
    fiscal_year_start_month: int,
    week_start: int,
    now: datetime,
    opening_date: date,
    date_from: date | None = None,
    date_to: date | None = None,
    as_of: date | None = None,
) -> ResolvedPeriod:
    if not 1 <= fiscal_year_start_month <= 12 or not 0 <= week_start <= 6:
        raise InvalidInput()
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        raise InvalidInput() from None
    if now.tzinfo is None:
        raise InvalidInput()
    today = now.astimezone(UTC).astimezone(zone).date()
    if opening_date > today:
        raise InvalidInput()
    if preset == "CUSTOM":
        if mode == "RANGE":
            if (
                date_from is None
                or date_to is None
                or as_of is not None
                or date_from > date_to
                or date_from < opening_date
                or date_to > today
            ):
                raise InvalidInput()
            return ResolvedPeriod(preset, mode, timezone, date_from, date_to, None)
        if (
            as_of is None
            or as_of < opening_date
            or as_of > today
            or date_from is not None
            or date_to is not None
        ):
            raise InvalidInput()
        return ResolvedPeriod(preset, mode, timezone, None, None, as_of)
    if date_from is not None or date_to is not None or as_of is not None:
        raise InvalidInput()
    if preset == "TODAY":
        start = end = today
    elif preset == "THIS_WEEK":
        start = today - timedelta(days=(today.weekday() - week_start) % 7)
        end = start + timedelta(days=6)
    elif preset == "THIS_MONTH":
        start = today.replace(day=1)
        next_month = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
        end = next_month - timedelta(days=1)
    elif preset == "THIS_YEAR":
        year = today.year if today.month >= fiscal_year_start_month else today.year - 1
        start = date(year, fiscal_year_start_month, 1)
        end = date(year + 1, fiscal_year_start_month, 1) - timedelta(days=1)
    else:
        raise InvalidInput()
    if mode == "AS_OF":
        return ResolvedPeriod(preset, mode, timezone, None, None, min(end, today))
    if end < opening_date:
        raise InvalidInput()
    return ResolvedPeriod(
        preset, mode, timezone, max(start, opening_date), end, None, start < opening_date
    )
