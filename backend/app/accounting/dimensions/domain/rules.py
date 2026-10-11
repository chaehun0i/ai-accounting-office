"""입력 규칙과 전표 분석축 검증을 결정론적으로 적용합니다."""

import re
from datetime import date
from uuid import UUID

from app.accounting.dimensions.domain.entities import Dimension, DimensionValue
from app.accounting.journals.domain.errors import AccountingError
from app.contracts.access_errors import InvalidInput

TYPES = ("BUSINESS_UNIT", "DEPARTMENT", "PROJECT", "COST_CENTER")


def validate_policy(
    dimensions: list[Dimension], kind: str, status: str, policy: str, resource: UUID | None = None
) -> None:
    if kind not in TYPES or policy not in ("OPTIONAL", "REQUIRED"):
        raise InvalidInput()
    if (
        status == "ACTIVE"
        and policy == "REQUIRED"
        and any(
            d.id != resource
            and d.dimension_type == kind
            and d.status == "ACTIVE"
            and d.required_policy == "REQUIRED"
            for d in dimensions
        )
    ):
        raise AccountingError(
            "DIMENSION_DUPLICATE_TYPE", "같은 분석 유형에는 필수 관리차원을 하나만 설정해 주세요."
        )


def validate_definition(code: str, name: str, status: str) -> None:
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,39}", code) or not 1 <= len(name.strip()) <= 200:
        raise InvalidInput()
    if status not in ("ACTIVE", "INACTIVE"):
        raise InvalidInput()


def validate_dates(start: date | None, end: date | None) -> None:
    if start and end and start > end:
        raise InvalidInput()


def validate_selection(
    company: UUID,
    entry_date: date,
    selected: tuple[UUID, ...],
    dimensions: list[Dimension],
    values: list[DimensionValue],
    *,
    enforce_required: bool = True,
) -> None:
    definitions = {d.id: d for d in dimensions if d.company_id == company}
    available = {v.id: v for v in values if v.company_id == company}
    seen_types: set[str] = set()
    seen_dimensions: set[UUID] = set()
    for identifier in selected:
        value = available.get(identifier)
        dimension = definitions.get(value.dimension_id) if value else None
        if (
            value is None
            or dimension is None
            or value.status != "ACTIVE"
            or dimension.status != "ACTIVE"
            or (value.effective_from and entry_date < value.effective_from)
            or (value.effective_to and entry_date > value.effective_to)
        ):
            raise AccountingError(
                "DIMENSION_VALUE_INVALID",
                "선택한 관리항목의 회사·사용 상태·적용 기간을 확인해 주세요.",
            )
        if dimension.dimension_type in seen_types or dimension.id in seen_dimensions:
            raise AccountingError(
                "DIMENSION_DUPLICATE_TYPE",
                "한 분개에는 같은 분석 유형의 항목을 하나만 선택해 주세요.",
            )
        seen_types.add(dimension.dimension_type)
        seen_dimensions.add(dimension.id)
    if enforce_required and any(
        d.status == "ACTIVE" and d.required_policy == "REQUIRED" and d.id not in seen_dimensions
        for d in definitions.values()
    ):
        raise AccountingError(
            "DIMENSION_VALUE_INVALID", "필수 관리차원의 항목을 각 분개에 선택해 주세요."
        )
