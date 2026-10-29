"""현금 범위와 사전 점검 응답의 타입 계약."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class CashFlowPolicy:
    id: UUID
    effective_from: date
    version: int
    interest_paid: str
    interest_received: str
    income_tax_paid: str
    effective_to: date | None = None
    status: str = "LATEST"


@dataclass(frozen=True)
class NonCashDisclosure:
    id: UUID
    journal_id: UUID
    debit_line_id: UUID
    credit_line_id: UUID
    evidence_id: UUID
    source_type: str
    amount: Decimal
    version: int


@dataclass(frozen=True)
class DisposalSource:
    id: UUID
    journal_id: UUID
    cash_line_id: UUID
    asset_line_id: UUID
    gain_line_id: UUID
    evidence_id: UUID
    proceeds: Decimal
    gain_amount: Decimal
    version: int


@dataclass(frozen=True)
class CashScope:
    id: UUID
    account_id: UUID
    scope_type: str
    effective_from: date
    effective_to: date | None
    version: int


@dataclass(frozen=True)
class CashClassification:
    id: UUID
    account_id: UUID
    activity_type: str
    line_code: str
    effective_from: date
    effective_to: date | None
    version: int


@dataclass(frozen=True)
class CashPreflightIssue:
    code: str
    journal_id: UUID | None = None


@dataclass(frozen=True)
class CashPreflight:
    period_id: UUID
    close_version: int
    source_digest: str
    mapping_digest: str
    opening_cash: Decimal
    closing_cash: Decimal
    net_cash_movement: Decimal
    net_operating: Decimal
    net_investing: Decimal
    net_financing: Decimal
    exchange_effect: Decimal
    classified_journal_count: int
    issues: tuple[CashPreflightIssue, ...]
    ready: bool


@dataclass(frozen=True)
class CashAllocation:
    id: UUID
    journal_id: UUID
    cash_line_id: UUID
    counterpart_line_id: UUID
    evidence_id: UUID
    amount: Decimal
    version: int
    replaces_id: UUID | None


@dataclass(frozen=True)
class CashEvent:
    journal_id: UUID
    cash_line_id: UUID
    cash_account_id: UUID
    counterpart_line_id: UUID
    counterpart_account_id: UUID
    activity_type: str
    line_code: str
    cash_inflow: Decimal
    cash_outflow: Decimal
    classification_id: UUID
    evidence_id: UUID | None
