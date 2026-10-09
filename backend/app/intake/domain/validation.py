"""원본 값을 오류에 복제하지 않는 결정적 검증과 정규화입니다."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.core.values import require_money
from app.intake.domain.canonical_fields import SCHEMAS, Mapping, SourceType
from app.intake.domain.workbook import Workbook


@dataclass(frozen=True)
class ValidationError:
    sheet_index: int
    row_number: int
    column_index: int
    error_code: str
    severity: str
    message: str
    canonical_field_code: str | None


@dataclass(frozen=True)
class CanonicalRow:
    sheet_index: int
    row_number: int
    source_id: str
    values: tuple[tuple[str, str], ...]


def value_for(kind: str, value: str) -> str:
    value = value.strip()
    if kind == "date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        return date.fromisoformat(value).isoformat()
    if kind == "decimal":
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            raise ValueError()
        amount = require_money(Decimal(value))
        return format(amount.quantize(Decimal("0.0001")), "f")
    if kind == "identifier" and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value):
        raise ValueError()
    if kind == "currency" and value not in {"KRW", "USD", "EUR", "JPY", "CNY", "GBP"}:
        raise ValueError()
    enums = {
        "direction": {"IN", "OUT"},
        "role": {"CUSTOMER", "SUPPLIER", "PAYEE", "TAX_COUNTERPARTY"},
        "payment_method": {"BANK", "CARD", "CASH", "OTHER"},
    }
    if kind in enums and value not in enums[kind]:
        raise ValueError()
    if kind == "business_number":
        value = value.replace("-", "")
        if not re.fullmatch(r"\d{10}", value):
            raise ValueError()
    return value


def validate(
    workbook: Workbook, source: SourceType, mappings: list[Mapping]
) -> tuple[list[CanonicalRow], list[ValidationError]]:
    errors: list[ValidationError] = []
    records: list[CanonicalRow] = []
    fields = {f.code: f for f in SCHEMAS[source]}
    seen: set[str] = set()
    for sheet in workbook.sheets:
        selected = [m for m in mappings if m.sheet_index == sheet.index]
        codes = {m.canonical_field_code for m in selected}
        for field in fields.values():
            if field.required and field.code not in codes:
                errors.append(
                    ValidationError(
                        sheet.index,
                        1,
                        0,
                        "REQUIRED_COLUMN_MISSING",
                        "ERROR",
                        "필수 항목을 원본 열에 연결해 주세요.",
                        field.code,
                    )
                )
        for mapping in selected:
            if mapping.status == "AMBIGUOUS":
                errors.append(
                    ValidationError(
                        sheet.index,
                        1,
                        mapping.column_index,
                        "MAPPING_AMBIGUOUS",
                        "ERROR",
                        "모호한 열을 직접 확인해 주세요.",
                        None,
                    )
                )
        for row_no, row in enumerate(sheet.rows, 2):
            values: dict[str, str] = {}
            before = len(errors)
            for mapping in selected:
                code = mapping.canonical_field_code
                if code is None:
                    continue
                field = fields[code]
                raw = row[mapping.column_index]
                if not raw.strip() and not field.required:
                    continue
                try:
                    if not raw.strip():
                        raise ValueError()
                    values[code] = value_for(field.kind, raw)
                except (ValueError, InvalidOperation):
                    errors.append(
                        ValidationError(
                            sheet.index,
                            row_no,
                            mapping.column_index,
                            "INVALID_FIELD_VALUE",
                            "ERROR",
                            "값의 필수 여부와 형식을 확인해 주세요.",
                            code,
                        )
                    )
            identity = values.get("source_id", "")
            if identity and identity in seen:
                errors.append(
                    ValidationError(
                        sheet.index,
                        row_no,
                        0,
                        "DUPLICATE_SOURCE_ID",
                        "ERROR",
                        "파일 안의 원본 자료 ID가 중복됩니다.",
                        "source_id",
                    )
                )
            seen.add(identity)
            if len(errors) == before:
                records.append(
                    CanonicalRow(sheet.index, row_no, identity, tuple(sorted(values.items())))
                )
    return records, errors
