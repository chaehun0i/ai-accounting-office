"""월마감 실행·검사·조정·사람 승인·명령 이력의 관계형 정본입니다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class ClosingRunModel(UUIDPrimaryKey, Base):
    __tablename__ = "closing_runs"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    accounting_period_id: Mapped[UUID]
    run_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(24))
    source_digest: Mapped[str] = mapped_column(String(64))
    unadjusted_tb_digest: Mapped[str] = mapped_column(String(64))
    adjusted_tb_digest: Mapped[str | None] = mapped_column(String(64))
    bank_reconciliation_digest: Mapped[str] = mapped_column(String(64))
    ar_reconciliation_digest: Mapped[str] = mapped_column(String(64))
    ap_reconciliation_digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "accounting_period_id", "run_version"),
        Index(
            "uq_closing_active_period",
            "company_id",
            "accounting_period_id",
            unique=True,
            postgresql_where=text("status IN ('ACTIVE','SUBMITTED','APPROVED')"),
        ),
        ForeignKeyConstraint(
            ["company_id", "accounting_period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("run_version >= 1", name="version"),
        CheckConstraint(
            "status IN ('ACTIVE','SUBMITTED','APPROVED','COMPLETED','SUPERSEDED')", name="status"
        ),
    )


class ClosingCheckModel(UUIDPrimaryKey, Base):
    __tablename__ = "closing_checks"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    closing_run_id: Mapped[UUID]
    check_version: Mapped[int]
    check_code: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(12))
    result_code: Mapped[str] = mapped_column(String(48))
    amount_impact: Mapped[Decimal]
    source_type: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[UUID | None]
    evidence_ref: Mapped[UUID | None]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "closing_run_id", "check_version", "check_code"),
        Index("ix_closing_checks_company_run", "company_id", "closing_run_id"),
        ForeignKeyConstraint(
            ["company_id", "closing_run_id"],
            ["closing_runs.company_id", "closing_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_ref"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("severity IN ('PASS','WARNING','BLOCKER')", name="severity"),
        CheckConstraint("check_version >= 1", name="version"),
        CheckConstraint("amount_impact >= 0", name="amount"),
    )


class ClosingAdjustmentModel(UUIDPrimaryKey, Base):
    __tablename__ = "closing_adjustments"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    closing_run_id: Mapped[UUID]
    adjustment_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    source_type: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[UUID | None]
    proposed_journal_id: Mapped[UUID]
    approval_id: Mapped[UUID | None]
    required: Mapped[bool] = mapped_column(server_default=text("true"))
    auto_reverse: Mapped[bool] = mapped_column(server_default=text("false"))
    scheduled_reversal_date: Mapped[date | None]
    reversal_journal_id: Mapped[UUID | None]
    version: Mapped[int] = mapped_column(server_default=text("1"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "proposed_journal_id"),
        Index("ix_closing_adjustments_company_run", "company_id", "closing_run_id"),
        ForeignKeyConstraint(
            ["company_id", "closing_run_id"],
            ["closing_runs.company_id", "closing_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "proposed_journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "approval_id"],
            ["approvals.company_id", "approvals.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "reversal_journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "adjustment_type IN ('ACCRUED_EXPENSE','ACCRUED_REVENUE',"
            "'PREPAID_EXPENSE_RELEASE','UNEARNED_REVENUE_RELEASE',"
            "'MANUAL_CUTOFF_ADJUSTMENT')",
            name="type",
        ),
        CheckConstraint("status IN ('PROPOSED','POSTED','REVERSED')", name="status"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "NOT auto_reverse OR scheduled_reversal_date IS NOT NULL", name="reversal_date"
        ),
    )


class ClosingApprovalModel(UUIDPrimaryKey, Base):
    __tablename__ = "closing_approvals"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    closing_run_id: Mapped[UUID]
    action_code: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    target_digest: Mapped[str] = mapped_column(String(64))
    requester_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewer_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    requested_at: Mapped[datetime]
    decided_at: Mapped[datetime | None]
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        Index("ix_closing_approvals_company_run", "company_id", "closing_run_id"),
        ForeignKeyConstraint(
            ["company_id", "closing_run_id"],
            ["closing_runs.company_id", "closing_runs.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("action_code IN ('CLOSE','REOPEN')", name="action"),
        CheckConstraint("status IN ('PENDING','APPROVED','CONSUMED','REJECTED')", name="status"),
        CheckConstraint("reviewer_id IS NULL OR reviewer_id <> requester_id", name="separation"),
    )


class ClosingEventModel(UUIDPrimaryKey, Base):
    __tablename__ = "closing_events"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    closing_run_id: Mapped[UUID]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    command_code: Mapped[str] = mapped_column(String(40))
    before_digest: Mapped[str] = mapped_column(String(64))
    after_digest: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime]
    __table_args__ = (
        Index("ix_closing_events_company_run", "company_id", "closing_run_id"),
        ForeignKeyConstraint(
            ["company_id", "closing_run_id"],
            ["closing_runs.company_id", "closing_runs.id"],
            ondelete="RESTRICT",
        ),
    )


class ClosingCommandModel(UUIDPrimaryKey, Base):
    __tablename__ = "closing_commands"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    command_code: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    closing_run_id: Mapped[UUID]
    adjustment_id: Mapped[UUID | None]
    approval_id: Mapped[UUID | None]
    occurred_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "command_code", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "closing_run_id"],
            ["closing_runs.company_id", "closing_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "adjustment_id"],
            ["closing_adjustments.company_id", "closing_adjustments.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "approval_id"],
            ["closing_approvals.company_id", "closing_approvals.id"],
            ondelete="RESTRICT",
        ),
    )
