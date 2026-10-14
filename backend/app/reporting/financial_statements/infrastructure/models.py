"""재무제표 taxonomy, 계정 매핑, 불변 스냅샷과 행별 원장 출처."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class ReportTaxonomyModel(UUIDPrimaryKey, Base):
    __tablename__ = "report_taxonomies"
    framework_code: Mapped[str] = mapped_column(String(32))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(12))
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    __table_args__ = (
        UniqueConstraint("framework_code", "version"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="dates"),
    )


class ReportLineModel(UUIDPrimaryKey, Base):
    __tablename__ = "report_lines"
    taxonomy_id: Mapped[UUID] = mapped_column(
        ForeignKey("report_taxonomies.id", ondelete="RESTRICT")
    )
    statement_type: Mapped[str] = mapped_column(String(24))
    line_code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(100))
    parent_line_id: Mapped[UUID | None]
    display_order: Mapped[int]
    normal_sign: Mapped[str] = mapped_column(String(6))
    subtotal_type: Mapped[str] = mapped_column(String(12))
    __table_args__ = (
        UniqueConstraint("taxonomy_id", "id"),
        UniqueConstraint("taxonomy_id", "line_code"),
        ForeignKeyConstraint(
            ["taxonomy_id", "parent_line_id"],
            ["report_lines.taxonomy_id", "report_lines.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "statement_type IN ('BALANCE_SHEET','INCOME_STATEMENT')", name="statement_type"
        ),
        CheckConstraint("normal_sign IN ('DEBIT','CREDIT')", name="normal_sign"),
        CheckConstraint("subtotal_type IN ('LEAF','DERIVED','TOTAL')", name="subtotal_type"),
        CheckConstraint("display_order > 0", name="display_order"),
    )


class ReportAccountMappingModel(UUIDPrimaryKey, Base):
    __tablename__ = "report_account_mappings"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    taxonomy_id: Mapped[UUID]
    account_id: Mapped[UUID]
    report_line_id: Mapped[UUID]
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    version: Mapped[int] = mapped_column(server_default=text("1"))
    __table_args__ = (
        UniqueConstraint("company_id", "taxonomy_id", "account_id"),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["taxonomy_id", "report_line_id"],
            ["report_lines.taxonomy_id", "report_lines.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_report_mappings_company_line", "company_id", "report_line_id"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="dates"),
    )


class StatementSetModel(UUIDPrimaryKey, Base):
    __tablename__ = "financial_statement_sets"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    period_id: Mapped[UUID]
    closing_run_id: Mapped[UUID]
    close_version: Mapped[int]
    taxonomy_id: Mapped[UUID] = mapped_column(
        ForeignKey("report_taxonomies.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(16))
    trial_balance_digest: Mapped[str] = mapped_column(String(64))
    mapping_digest: Mapped[str] = mapped_column(String(64))
    generated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    generated_at: Mapped[datetime]
    version: Mapped[int] = mapped_column(server_default=text("1"))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint(
            "company_id",
            "period_id",
            "close_version",
            "taxonomy_id",
            "trial_balance_digest",
            "mapping_digest",
        ),
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "closing_run_id"],
            ["closing_runs.company_id", "closing_runs.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status = 'GENERATED'", name="status"),
        CheckConstraint("close_version >= 1 AND version >= 1", name="version"),
    )


class StatementModel(UUIDPrimaryKey, Base):
    __tablename__ = "financial_statements"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    statement_set_id: Mapped[UUID]
    statement_type: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16))
    snapshot_digest: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "statement_set_id", "statement_type"),
        ForeignKeyConstraint(
            ["company_id", "statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "statement_type IN ('BALANCE_SHEET','INCOME_STATEMENT')", name="statement_type"
        ),
        CheckConstraint("status = 'GENERATED'", name="status"),
    )


class StatementSnapshotModel(UUIDPrimaryKey, Base):
    __tablename__ = "financial_statement_snapshots"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    statement_id: Mapped[UUID]
    statement_version: Mapped[int]
    source_digest: Mapped[str] = mapped_column(String(64))
    mapping_digest: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "statement_id", "statement_version"),
        ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["financial_statements.company_id", "financial_statements.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("statement_version >= 1", name="version"),
    )


class StatementLineModel(UUIDPrimaryKey, Base):
    __tablename__ = "financial_statement_lines"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    snapshot_id: Mapped[UUID]
    report_line_id: Mapped[UUID] = mapped_column(ForeignKey("report_lines.id", ondelete="RESTRICT"))
    current_amount: Mapped[Decimal]
    source_digest: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "snapshot_id", "report_line_id"),
        ForeignKeyConstraint(
            ["company_id", "snapshot_id"],
            ["financial_statement_snapshots.company_id", "financial_statement_snapshots.id"],
            ondelete="RESTRICT",
        ),
    )


class StatementSourceModel(UUIDPrimaryKey, Base):
    __tablename__ = "financial_statement_sources"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    statement_line_id: Mapped[UUID]
    account_id: Mapped[UUID]
    journal_line_id: Mapped[UUID]
    amount: Mapped[Decimal]
    __table_args__ = (
        UniqueConstraint("company_id", "statement_line_id", "journal_line_id"),
        ForeignKeyConstraint(
            ["company_id", "statement_line_id"],
            ["financial_statement_lines.company_id", "financial_statement_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "journal_line_id"],
            ["journal_lines.company_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_statement_sources_company_line", "company_id", "statement_line_id"),
    )


class StatementCommandModel(UUIDPrimaryKey, Base):
    __tablename__ = "financial_statement_commands"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    command_code: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    statement_set_id: Mapped[UUID]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "command_code", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
    )
