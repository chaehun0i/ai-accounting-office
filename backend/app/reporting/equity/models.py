"""Company-scoped equity classification and immutable SCE facts."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class EquityComponentModel(UUIDPrimaryKey, Base):
    __tablename__ = "equity_components"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    component_code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(100))
    component_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(12))
    display_order: Mapped[int]
    version: Mapped[int]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "component_code"),
        CheckConstraint(
            "component_type IN ('CONTRIBUTED_CAPITAL','RETAINED_EARNINGS',"
            "'TREASURY_STOCK','OTHER_EQUITY','OCI_COMPONENT')",
            name="type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','INACTIVE') AND display_order > 0 AND version > 0", name="state"
        ),
    )


class EquityAccountMappingModel(UUIDPrimaryKey, Base):
    __tablename__ = "equity_account_mappings"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    component_id: Mapped[UUID]
    account_id: Mapped[UUID]
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    status: Mapped[str] = mapped_column(String(12))
    version: Mapped[int]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "account_id", "version"),
        ForeignKeyConstraint(
            ["company_id", "component_id"],
            ["equity_components.company_id", "equity_components.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="dates"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE') AND version > 0", name="state"),
    )


class EquityEventModel(UUIDPrimaryKey, Base):
    __tablename__ = "equity_events"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    component_id: Mapped[UUID]
    event_date: Mapped[date]
    event_type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    source_journal_id: Mapped[UUID]
    source_journal_line_id: Mapped[UUID]
    approval_id: Mapped[UUID]
    mapping_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(12))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "source_journal_line_id"),
        ForeignKeyConstraint(
            ["company_id", "component_id"],
            ["equity_components.company_id", "equity_components.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "source_journal_id", "source_journal_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "approval_id"],
            ["approvals.company_id", "approvals.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_type IN ('CAPITAL_CONTRIBUTION','CAPITAL_REDUCTION','DIVIDEND',"
            "'TREASURY_STOCK_ACQUIRE','TREASURY_STOCK_DISPOSE','PROFIT_TRANSFER',"
            "'OCI_TRANSFER','OTHER_ADJUSTMENT')",
            name="type",
        ),
        CheckConstraint("status = 'VERIFIED' AND mapping_version > 0", name="state"),
    )


class DividendDeclarationModel(UUIDPrimaryKey, Base):
    __tablename__ = "dividend_declarations"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    resolution_date: Mapped[date]
    payable_date: Mapped[date | None]
    total_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    status: Mapped[str] = mapped_column(String(12))
    approval_id: Mapped[UUID | None]
    source_journal_id: Mapped[UUID | None]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        ForeignKeyConstraint(
            ["company_id", "approval_id"],
            ["approvals.company_id", "approvals.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "source_journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "total_amount > 0 AND (payable_date IS NULL OR payable_date >= resolution_date)",
            name="amount_dates",
        ),
        CheckConstraint("status IN ('PROPOSED','APPROVED','CANCELLED')", name="status"),
        CheckConstraint(
            "status <> 'APPROVED' OR (approval_id IS NOT NULL AND source_journal_id IS NOT NULL)",
            name="approved_source",
        ),
    )


class DividendPaymentModel(UUIDPrimaryKey, Base):
    __tablename__ = "dividend_payments"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    declaration_id: Mapped[UUID]
    cash_flow_statement_id: Mapped[UUID]
    cash_flow_event_id: Mapped[UUID]
    journal_id: Mapped[UUID]
    payment_date: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "cash_flow_event_id"),
        ForeignKeyConstraint(
            ["company_id", "declaration_id"],
            ["dividend_declarations.company_id", "dividend_declarations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "cash_flow_statement_id", "cash_flow_event_id"],
            ["cash_flow_events.company_id", "cash_flow_events.statement_id", "cash_flow_events.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="amount"),
    )


class EquityStatementModel(UUIDPrimaryKey, Base):
    __tablename__ = "statement_of_changes_in_equity"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    statement_set_id: Mapped[UUID]
    period_id: Mapped[UUID]
    close_version: Mapped[int]
    balance_sheet_digest: Mapped[str] = mapped_column(String(64))
    income_statement_digest: Mapped[str] = mapped_column(String(64))
    mapping_digest: Mapped[str] = mapped_column(String(64))
    event_digest: Mapped[str] = mapped_column(String(64))
    source_digest: Mapped[str] = mapped_column(String(64))
    snapshot_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    generated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    generated_at: Mapped[datetime]
    generation_transaction: Mapped[int] = mapped_column(
        BigInteger, server_default=text("txid_current()")
    )
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "period_id", "snapshot_digest"),
        ForeignKeyConstraint(
            ["company_id", "statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status = 'RECONCILED' AND close_version > 0", name="status"),
    )


class EquityStatementLineModel(UUIDPrimaryKey, Base):
    __tablename__ = "equity_statement_lines"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    statement_id: Mapped[UUID]
    component_id: Mapped[UUID]
    movement_type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    display_order: Mapped[int]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "statement_id", "component_id", "movement_type"),
        ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["statement_of_changes_in_equity.company_id", "statement_of_changes_in_equity.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "component_id"],
            ["equity_components.company_id", "equity_components.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "movement_type IN ('OPENING','OWNER_TRANSACTIONS','PROFIT_OR_LOSS',"
            "'OTHER_COMPREHENSIVE_INCOME','OTHER_ADJUSTMENTS','CLOSING')",
            name="movement",
        ),
    )


class EquityStatementSourceModel(UUIDPrimaryKey, Base):
    __tablename__ = "equity_statement_sources"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    statement_line_id: Mapped[UUID]
    journal_line_id: Mapped[UUID | None]
    income_statement_id: Mapped[UUID | None]
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "statement_line_id"],
            ["equity_statement_lines.company_id", "equity_statement_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "journal_line_id"],
            ["journal_lines.company_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "income_statement_id"],
            ["financial_statements.company_id", "financial_statements.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(journal_line_id IS NULL) <> (income_statement_id IS NULL)", name="one_source"
        ),
    )


class EquityCommandModel(UUIDPrimaryKey, Base):
    __tablename__ = "equity_statement_commands"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    statement_id: Mapped[UUID]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["statement_of_changes_in_equity.company_id", "statement_of_changes_in_equity.id"],
            ondelete="RESTRICT",
        ),
    )
