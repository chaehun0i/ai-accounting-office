"""수금·지급은 원천 전표와 분리된 업무 사건입니다."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class Allocation:
    target_id: UUID
    allocated_amount: Decimal
    expected_version: int


@dataclass(frozen=True, kw_only=True)
class Settlement:
    id: UUID
    company_id: UUID
    journal_entry_id: UUID
    settlement_date: date
    total_amount: Decimal
    currency_code: str
    method: str
    reference_no: str
    status: str
    version: int
    unapplied_amount: Decimal
    allocations: tuple[Allocation, ...]
