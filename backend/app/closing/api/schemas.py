"""결산 명령에는 회사·권한·기간 상태를 임의 지정하는 필드를 두지 않습니다."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.accounting.journals.api.schemas import LineCreate


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Start(Input):
    accounting_period_id: UUID


class AdjustmentCreate(Input):
    adjustment_type: Literal[
        "ACCRUED_EXPENSE",
        "ACCRUED_REVENUE",
        "PREPAID_EXPENSE_RELEASE",
        "UNEARNED_REVENUE_RELEASE",
        "MANUAL_CUTOFF_ADJUSTMENT",
    ]
    entry_date: date
    description: str = Field(min_length=1, max_length=2000)
    lines: list[LineCreate] = Field(min_length=2, max_length=200)
    auto_reverse: bool = False
    scheduled_reversal_date: date | None = None


class ApprovalRequest(Input):
    reason: str = Field(min_length=1, max_length=2000)


class ApprovalDecision(ApprovalRequest):
    pass


class Finish(Input):
    approval_id: UUID


class Reopen(Finish):
    reason: str = Field(min_length=1, max_length=2000)


class Reversal(Input):
    reason: str = Field(min_length=1, max_length=2000)


class CheckRead(BaseModel):
    check_code: str
    severity: str
    result_code: str
    amount_impact: Decimal
    source_type: str | None
    source_id: UUID | None
    evidence_ref: UUID | None


class AdjustmentRead(BaseModel):
    id: UUID
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


class RunRead(BaseModel):
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


class RunDetail(RunRead):
    checks: list[CheckRead]
    adjustments: list[AdjustmentRead]


class ApprovalRead(BaseModel):
    id: UUID
    closing_run_id: UUID
    action_code: str
    status: str
    target_digest: str
    requester_id: UUID
    reviewer_id: UUID | None
    requested_at: datetime
    decided_at: datetime | None
    reason: str


class TrialBalanceRead(BaseModel):
    stage: str
    digest: str
    rows: list[dict[str, str | Decimal | UUID]]
