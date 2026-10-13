"""월마감 결과의 읽기 계약입니다."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class ClosingRun:
    id: UUID
    company_id: UUID
    accounting_period_id: UUID
    run_version: int
    status: str
    source_digest: str
    unadjusted_tb_digest: str
    adjusted_tb_digest: str | None
    bank_reconciliation_digest: str
    ar_reconciliation_digest: str
    ap_reconciliation_digest: str
    created_by: UUID
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, kw_only=True)
class ClosingCheckResult:
    check_code: str
    severity: str
    result_code: str
    amount_impact: Decimal
    source_type: str | None
    source_id: UUID | None
    evidence_ref: UUID | None


@dataclass(frozen=True, kw_only=True)
class ClosingAdjustment:
    id: UUID
    company_id: UUID
    closing_run_id: UUID
    adjustment_type: str
    status: str
    proposed_journal_id: UUID
    approval_id: UUID | None
    required: bool
    auto_reverse: bool
    scheduled_reversal_date: date | None
    reversal_journal_id: UUID | None
    version: int


@dataclass(frozen=True, kw_only=True)
class ClosingApproval:
    id: UUID
    company_id: UUID
    closing_run_id: UUID
    action_code: str
    status: str
    target_digest: str
    requester_id: UUID
    reviewer_id: UUID | None
    requested_at: datetime
    decided_at: datetime | None
    reason: str


@dataclass(frozen=True, kw_only=True)
class ClosingSnapshot:
    source_digest: str
    tb_digest: str
    bank_digest: str
    ar_digest: str
    ap_digest: str
    checks: tuple[ClosingCheckResult, ...]
