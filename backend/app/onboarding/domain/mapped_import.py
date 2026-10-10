"""자유 매핑 거래처 입력도 공식 양식과 같은 typed Draft로 연결합니다."""

from app.intake.domain.canonical_fields import Mapping, SourceType
from app.intake.domain.validation import validate
from app.intake.domain.workbook import Workbook
from app.onboarding.domain.catalog import BY_CODE
from app.onboarding.domain.errors import TemplateUnsupported
from app.onboarding.domain.validation import Issue
from app.onboarding.domain.values import Cell, parse_value


def mapped_cells(
    workbook: Workbook, source: SourceType, mappings: list[Mapping]
) -> tuple[list[Cell], list[Issue]]:
    if source != SourceType.COUNTERPARTY:
        raise TemplateUnsupported()
    rows, errors = validate(workbook, source, mappings)
    issues = [Issue(None, str(e.row_number), e.error_code, e.severity, e.message) for e in errors]
    cells: list[Cell] = []
    for row in rows:
        values = dict(row.values)
        key = values["source_id"]
        converted = {
            "counterparty_code": key,
            "legal_name": values.get("legal_name") or values["display_name"],
            "counterparty_type": "BUSINESS",
            "role_code": values["role_code"],
        }
        if values.get("business_number"):
            converted["business_number"] = values["business_number"]
        for code, raw in converted.items():
            field = BY_CODE[f"Counterparties.{code}"]
            cells.append(Cell(field.field_code, key, parse_value(field, raw), "EXCEL_IMPORT"))
    return cells, issues
