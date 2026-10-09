import re
import unicodedata
from datetime import date, timedelta
from enum import StrEnum

from app.contracts.access_errors import InvalidInput

CURRENCIES = frozenset(
    {"KRW", "USD", "EUR", "JPY", "GBP", "CAD", "AUD", "CHF", "CNY", "SGD", "HKD"}
)


class DueRule(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    NET_DAYS = "NET_DAYS"
    MONTH_END_PLUS_DAYS = "MONTH_END_PLUS_DAYS"


class CounterpartyType(StrEnum):
    BUSINESS = "BUSINESS"
    INDIVIDUAL = "INDIVIDUAL"
    OTHER = "OTHER"


class MasterStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"


class CounterpartyRole(StrEnum):
    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"
    PAYEE = "PAYEE"
    TAX_COUNTERPARTY = "TAX_COUNTERPARTY"


def normalized_identifier(value: str | None, length: int) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = re.sub(r"[-\s]", "", value)
    if not re.fullmatch(r"[0-9]{" + str(length) + "}", normalized):
        raise InvalidInput()
    return normalized


def normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def validate_currency(value: str) -> None:
    if value not in CURRENCIES:
        raise InvalidInput()


def due_date(
    invoice_date: date, rule: DueRule, days: int, contractual_due_date: date | None = None
) -> date:
    if days < 0 or days > 3650 or (rule == DueRule.IMMEDIATE and days != 0):
        raise InvalidInput()
    if contractual_due_date is not None:
        return contractual_due_date
    if rule == DueRule.IMMEDIATE:
        return invoice_date
    if rule == DueRule.MONTH_END_PLUS_DAYS:
        next_month = invoice_date.replace(day=28) + timedelta(days=4)
        invoice_date = next_month.replace(day=1) - timedelta(days=1)
    return invoice_date + timedelta(days=days)
