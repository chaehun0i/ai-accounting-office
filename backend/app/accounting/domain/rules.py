import calendar
import re
from datetime import date
from enum import StrEnum

from app.contracts.access_errors import InvalidInput


class AccountType(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class BalanceSide(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class ResetPolicy(StrEnum):
    FISCAL_YEAR = "FISCAL_YEAR"
    NEVER = "NEVER"


def validate_account(account_type: str, normal_balance: str, is_contra: bool = False) -> None:
    if account_type not in AccountType or normal_balance not in BalanceSide:
        raise InvalidInput()
    debit = account_type in {AccountType.ASSET, AccountType.EXPENSE}
    if is_contra:
        debit = not debit
    if (normal_balance == BalanceSide.DEBIT) != debit:
        raise InvalidInput()


def monthly_periods(fiscal_year: int, start_month: int) -> list[tuple[int, date, date]]:
    # fiscal_year는 회계연도가 시작하는 달력 연도입니다. 종료일은 포함합니다.
    if not 1900 <= fiscal_year <= 9998 or not 1 <= start_month <= 12:
        raise InvalidInput()
    periods = []
    for offset in range(12):
        year = fiscal_year + (start_month - 1 + offset) // 12
        month = (start_month - 1 + offset) % 12 + 1
        periods.append(
            (
                offset + 1,
                date(year, month, 1),
                date(year, month, calendar.monthrange(year, month)[1]),
            )
        )
    return periods


def journal_number(prefix: str, fiscal_year: int, number: int) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,9}", prefix) or number < 1:
        raise InvalidInput()
    if not 1900 <= fiscal_year <= 9998:
        raise InvalidInput()
    return f"{prefix}-{fiscal_year}-{number:06d}"


def validate_hierarchy(parents: dict[str, str | None]) -> None:
    for code in parents:
        seen: set[str] = set()
        current: str | None = code
        while current is not None:
            if current in seen or current not in parents:
                raise InvalidInput()
            seen.add(current)
            current = parents[current]
