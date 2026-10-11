"""채권과 채무가 공유하는 원천·잔액 조회 계약입니다."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class Obligation:
    id: UUID
    company_id: UUID
    counterparty_id: UUID
    counterparty_name: str
    origin_journal_id: UUID
    origin_line_no: int
    account_id: UUID
    original_amount: Decimal
    outstanding_amount: Decimal
    currency_code: str
    due_date: date
    status: str
    version: int
    origin_date: date
    source_transaction_id: UUID | None
    import_id: UUID | None
    evidence_ids: tuple[UUID, ...]
