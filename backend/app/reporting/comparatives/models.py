"""Relational comparative statement versions and display-only reclassifications."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class ComparativeStatementModel(UUIDPrimaryKey, Base):
    __tablename__ = "comparative_statement_snapshots"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    period_id: Mapped[UUID]
    comparison_period_id: Mapped[UUID]
    statement_set_id: Mapped[UUID]
    comparison_statement_set_id: Mapped[UUID]
    close_version: Mapped[int]
    comparison_close_version: Mapped[int]
    current_source_digest: Mapped[str] = mapped_column(String(64))
    comparison_source_digest: Mapped[str] = mapped_column(String(64))
    current_mapping_digest: Mapped[str] = mapped_column(String(64))
    comparison_mapping_digest: Mapped[str] = mapped_column(String(64))
    taxonomy_version: Mapped[int]
    source_digest: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewer_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    review_digest: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None]
    version: Mapped[int]

    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint(
            "company_id",
            "period_id",
            "comparison_period_id",
            "source_digest",
            "revision",
            name="uq_comparative_statement_sources",
        ),
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "comparison_period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "comparison_statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("period_id <> comparison_period_id", name="different_periods"),
        CheckConstraint(
            "status IN ('DRAFT','REVIEW_REQUESTED','APPROVED','REJECTED','SUPERSEDED')",
            name="status",
        ),
        CheckConstraint("close_version > 0 AND comparison_close_version > 0", name="close_version"),
        CheckConstraint("taxonomy_version > 0 AND version > 0", name="version"),
        CheckConstraint(
            "(status = 'APPROVED' AND reviewer_id IS NOT NULL AND approved_at IS NOT NULL "
            "AND review_digest IS NOT NULL) OR (status <> 'APPROVED' AND approved_at IS NULL)",
            name="approval_fields",
        ),
        Index("ix_comparative_statements_company_period", "company_id", "period_id"),
    )


class ComparativeReclassificationModel(UUIDPrimaryKey, Base):
    __tablename__ = "comparative_reclassifications"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    comparative_statement_id: Mapped[UUID]
    statement_type: Mapped[str] = mapped_column(String(24))
    from_line_code: Mapped[str] = mapped_column(String(40))
    to_line_code: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]

    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        ForeignKeyConstraint(
            ["company_id", "comparative_statement_id"],
            ["comparative_statement_snapshots.company_id", "comparative_statement_snapshots.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "statement_type IN ('BALANCE_SHEET','INCOME_STATEMENT')", name="statement_type"
        ),
        CheckConstraint("from_line_code <> to_line_code", name="different_lines"),
        CheckConstraint("amount <> 0", name="nonzero_amount"),
        CheckConstraint("length(trim(reason)) > 0", name="reason"),
        Index("ix_comparative_reclass_company_snapshot", "company_id", "comparative_statement_id"),
    )


class ComparativeStatementAuditModel(UUIDPrimaryKey, Base):
    __tablename__ = "comparative_statement_audit_events"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    comparative_statement_id: Mapped[UUID]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    expected_version: Mapped[int]
    created_at: Mapped[datetime]

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "comparative_statement_id"],
            ["comparative_statement_snapshots.company_id", "comparative_statement_snapshots.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("expected_version > 0", name="expected_version"),
        Index("ix_comparative_audit_company_snapshot", "company_id", "comparative_statement_id"),
    )
