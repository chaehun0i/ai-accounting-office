"""관리차원은 금액과 계정 분류를 바꾸지 않는 회사별 분석축입니다."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class Dimension:
    id: UUID
    company_id: UUID
    dimension_code: str
    name: str
    dimension_type: str
    status: str
    required_policy: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class DimensionValue:
    id: UUID
    company_id: UUID
    dimension_id: UUID
    value_code: str
    name: str
    parent_value_id: UUID | None
    status: str
    effective_from: date | None
    effective_to: date | None
    version: int
    created_at: datetime
    updated_at: datetime
