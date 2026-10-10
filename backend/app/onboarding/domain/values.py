"""외부 입력을 명시적 자료형으로 검증하고 안정적인 행 키를 계산합니다."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.core.values import require_money
from app.onboarding.domain.catalog import BY_CODE, ENUMS, KEYS, Field
from app.onboarding.domain.errors import InvalidValue

Scalar = str | Decimal | date | bool


@dataclass(frozen=True)
class Cell:
    field_code: str
    row_key: str
    value: Scalar
    source_type: str = "MANUAL"
    status: str = "VALID"
    version: int = 1


def parse_value(field: Field, raw: object) -> Scalar:
    try:
        if field.data_type == "NUMERIC":
            if isinstance(raw, (float, bool)) or not isinstance(raw, (str, Decimal, int)):
                raise InvalidValue()
            value = require_money(Decimal(raw))
            short = field.field_code.split(".")[1]
            if short == "fiscal_year_start_month" and (value != int(value) or not 1 <= value <= 12):
                raise InvalidValue()
            if short.endswith(("amount", "cost", "quantity", "months")) and value < 0:
                raise InvalidValue()
            return value
        if field.data_type == "DATE":
            if isinstance(raw, date):
                return raw
            if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                raise InvalidValue()
            return date.fromisoformat(raw)
        if field.data_type == "BOOLEAN":
            if type(raw) is bool:
                return raw
            if isinstance(raw, str) and raw in {"true", "false", "TRUE", "FALSE"}:
                return raw.lower() == "true"
            raise InvalidValue()
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 500:
            raise InvalidValue()
        value_text = raw.strip()
        if field.enum_source_code and value_text not in ENUMS[field.enum_source_code]:
            raise InvalidValue()
        short = field.field_code.split(".")[1]
        if short in {"business_number", "corporation_number"}:
            value_text = value_text.replace("-", "")
            if not re.fullmatch(r"\d{10}" if short == "business_number" else r"\d{13}", value_text):
                raise InvalidValue()
        if short.endswith("_code") and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value_text):
            raise InvalidValue()
        if short == "external_reference" and (
            value_text.isdigit() or not value_text.startswith("vault:")
        ):
            raise InvalidValue()
        return value_text
    except (ValueError, TypeError, InvalidOperation):
        raise InvalidValue() from None


def row_key(section: str, row: dict[str, Scalar]) -> str:
    if section not in KEYS:
        return "singleton"
    keys = KEYS[section]
    values = [str(row.get(key, "")) for key in keys]
    if any(
        not value
        for key, value in zip(keys, values, strict=True)
        if key != "counterparty_code" or section != "Opening_Balances"
    ):
        raise InvalidValue()
    if any("|" in v for v in values) or sum(map(len, values)) > 250:
        raise InvalidValue()
    return "|".join(values)


def required(field: Field, cells: list[Cell]) -> bool:
    if field.required_rule_code == "ALWAYS":
        return True
    return field.required_rule_code == "CORPORATION" and any(
        c.field_code == "Company.taxpayer_type" and c.value == "CORPORATION" for c in cells
    )


def classify(current: Cell | None, incoming: Cell) -> str:
    if current is None:
        return "APPLY"
    return "UNCHANGED" if current.value == incoming.value else "CONFLICT"


def editable(field_code: str) -> Field:
    field = BY_CODE.get(field_code)
    if field is None or not field.active or field.input_mode == "DERIVED_READONLY":
        raise InvalidValue()
    return field
