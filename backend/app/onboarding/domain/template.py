"""공식 양식의 버전과 Sheet 계약은 애플리케이션 버전과 독립적입니다."""

from datetime import datetime

from app.intake.domain.workbook import Workbook
from app.onboarding.domain.catalog import CATALOG, SECTIONS, Field
from app.onboarding.domain.errors import InvalidValue, TemplateUnsupported
from app.onboarding.domain.validation import Issue
from app.onboarding.domain.values import Cell, Scalar, parse_value, row_key

TEMPLATE_CODE = "ACCOUNTING_ONBOARDING"
TEMPLATE_VERSION = "1"
SCHEMA_VERSION = "1"
LOCALE = "ko-KR"


def sheet_fields(section: str) -> tuple[Field, ...]:
    return tuple(
        f for f in CATALOG if f.section_code == section and f.input_mode != "DERIVED_READONLY"
    )


def read_template(workbook: Workbook) -> tuple[dict[str, str], list[Cell], list[Issue]]:
    sheets = {s.name: s for s in workbook.sheets}
    metadata_sheet = sheets.get("Metadata")
    if metadata_sheet is None or metadata_sheet.headers != ("key", "value"):
        raise TemplateUnsupported()
    metadata = {row[0]: row[1] for row in metadata_sheet.rows}
    if (
        len(metadata) != len(metadata_sheet.rows)
        or metadata.get("template_code") != TEMPLATE_CODE
        or metadata.get("template_version") != TEMPLATE_VERSION
        or metadata.get("schema_version") != SCHEMA_VERSION
        or metadata.get("locale") != LOCALE
    ):
        raise TemplateUnsupported()
    try:
        generated = datetime.fromisoformat(metadata["generated_at"])
        if generated.tzinfo is None:
            raise ValueError
    except (ValueError, KeyError):
        raise TemplateUnsupported() from None
    if set(sheets) - set(SECTIONS) - {"README", "Metadata"}:
        raise TemplateUnsupported()
    cells: list[Cell] = []
    errors: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    for name, sheet in sheets.items():
        if name not in SECTIONS:
            continue
        fields = sheet_fields(name)
        columns = {f.field_code.split(".")[1]: f for f in fields}
        if set(sheet.headers) != set(columns):
            raise TemplateUnsupported()
        for number, values in enumerate(sheet.rows, 2):
            if not any(v.strip() for v in values):
                continue
            row: dict[str, Scalar] = {}
            invalid = False
            for code, raw in zip(sheet.headers, values, strict=True):
                if not raw.strip():
                    continue
                try:
                    row[code] = parse_value(columns[code], raw)
                except InvalidValue:
                    invalid = True
                    errors.append(
                        Issue(
                            columns[code].field_code,
                            str(number),
                            "INVALID_VALUE",
                            "ERROR",
                            "입력값의 형식을 확인해 주세요.",
                        )
                    )
            try:
                key = row_key(name, row)
                if (name, key) in seen:
                    raise InvalidValue()
                seen.add((name, key))
                if not invalid:
                    cells.extend(
                        Cell(columns[code].field_code, key, value, "EXCEL_IMPORT")
                        for code, value in row.items()
                    )
            except InvalidValue:
                errors.append(
                    Issue(
                        None,
                        f"{name}:{number}",
                        "DUPLICATE_OR_MISSING_KEY",
                        "ERROR",
                        "행 식별키의 누락 또는 중복을 확인해 주세요.",
                    )
                )
    return metadata, cells, errors
