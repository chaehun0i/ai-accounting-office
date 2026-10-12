"""은행과 카드가 공유하는 회사 범위 원천 조회 계약입니다."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class FinancialAccount:
    id: UUID
    company_id: UUID
    kind: str
    institution_code: str
    alias: str
    control_account_id: UUID
    currency_code: str = "KRW"
    status: str = "ACTIVE"
    version: int = 1


@dataclass(frozen=True, kw_only=True)
class FinancialSource:
    id: UUID
    company_id: UUID
    account_id: UUID
    kind: str
    source_system: str
    source_id: str
    source_fingerprint: str
    occurred_at: datetime
    direction: str
    amount: Decimal
    counterparty_text: str
    description: str
    reference: str
    source_import_id: UUID
    source_receipt_id: UUID
    sheet_index: int
    row_number: int
    source_status: str = "CAPTURED"
    balance_after: Decimal | None = None
    statement_id: UUID | None = None
    matched_amount: Decimal = Decimal("0")
    reconciliation_status: str = "UNMATCHED"
    version: int = 1


@dataclass(frozen=True, kw_only=True)
class Statement:
    id: UUID
    company_id: UUID
    bank_account_id: UUID
    statement_start: date
    statement_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    source_import_id: UUID
    source_receipt_id: UUID
    source_digest: str
    currency_code: str = "KRW"
    status: str = "IMPORTED"
    version: int = 1


@dataclass(frozen=True, kw_only=True)
class ReconciliationLine:
    source_type: str
    source_id: UUID
    target_type: str
    target_id: UUID
    amount: Decimal
    source_version: int
    target_version: int


@dataclass(frozen=True, kw_only=True)
class Match:
    id: UUID
    company_id: UUID
    match_type: str
    status: str
    matched_amount: Decimal
    version: int
    created_by: UUID
    lines: tuple[ReconciliationLine, ...]
    unmatch_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class ReconciliationItem:
    id: UUID
    company_id: UUID
    statement_id: UUID
    reason_code: str
    amount: Decimal
    status: str
    description: str


@dataclass(frozen=True, kw_only=True)
class StatementSummary:
    statement_id: UUID
    as_of: date
    account_id: UUID
    statement_balance: Decimal
    reconciled_source_balance: Decimal
    gl_balance: Decimal
    difference_amount: Decimal
    source_total: Decimal
    matched: Decimal
    review: int
    unmatched: int
    partial: int
    unmatched_count: int
    partial_count: int
    review_count: int
    reconciliation_item_count: int
    blocker: bool


@dataclass(frozen=True, kw_only=True)
class CardSummary:
    card_account_id: UUID
    account_id: UUID
    as_of: date
    source_balance: Decimal
    reconciled_source_balance: Decimal
    gl_balance: Decimal
    difference_amount: Decimal
    unmatched_count: int
    partial_count: int
    review_count: int
    blocker: bool
