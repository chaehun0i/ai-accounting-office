"""채권채무 잔액·배분은 회계금액을 반올림하거나 추정하지 않습니다."""

from datetime import date
from decimal import Decimal

from app.accounting.journals.domain.errors import AccountingError
from app.core.values import require_money

ZERO = Decimal("0")


def positive(amount: Decimal) -> Decimal:
    require_money(amount)
    if amount <= ZERO:
        raise AccountingError("BUSINESS_RULE_VIOLATION", "금액은 0보다 커야 합니다.")
    return amount


def outstanding(original: Decimal, allocated: Decimal) -> Decimal:
    require_money(original)
    require_money(allocated)
    if original < ZERO or allocated < ZERO or allocated > original:
        raise AccountingError(
            "SETTLEMENT_ALLOCATION_EXCEEDED", "배분 금액이 남은 금액을 초과합니다."
        )
    return original - allocated


def target_status(original: Decimal, allocated: Decimal) -> str:
    remaining = outstanding(original, allocated)
    return "SETTLED" if remaining == ZERO else "OPEN" if allocated == ZERO else "PARTIAL"


def aging_bucket(due: date, as_of: date) -> str:
    days = (as_of - due).days
    return (
        "CURRENT"
        if days <= 0
        else "1-30"
        if days <= 30
        else "31-60"
        if days <= 60
        else "61-90"
        if days <= 90
        else "90+"
    )


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise AccountingError(
            "SETTLEMENT_TARGET_STALE",
            "다른 작업으로 내용이 바뀌었습니다. 최신 내용을 확인해 주세요.",
            409,
        )
