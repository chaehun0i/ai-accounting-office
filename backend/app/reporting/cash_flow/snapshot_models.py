"""Append-only relational CF snapshots; every source FK retains company scope."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


def source_fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["company_id", column], [f"{table}.company_id", f"{table}.id"], ondelete="RESTRICT"
    )


class CashFlowStatementModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_statements"
    company_id: Mapped[UUID] = mapped_column(index=True)
    period_id: Mapped[UUID]
    statement_set_id: Mapped[UUID]
    balance_sheet_id: Mapped[UUID]
    balance_sheet_digest: Mapped[str] = mapped_column(String(64))
    income_statement_id: Mapped[UUID]
    income_statement_digest: Mapped[str] = mapped_column(String(64))
    close_version: Mapped[int]
    source_digest: Mapped[str] = mapped_column(String(64))
    mapping_digest: Mapped[str] = mapped_column(String(64))
    direct_mapping_digest: Mapped[str] = mapped_column(String(64))
    snapshot_digest: Mapped[str] = mapped_column(String(64))
    policy_code: Mapped[str] = mapped_column(String(40))
    policy_version: Mapped[int]
    method: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    opening_cash: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    closing_cash: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    net_profit: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    net_operating: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    net_investing: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    net_financing: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    exchange_effect: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    generated_by: Mapped[UUID]
    generated_at: Mapped[datetime]
    generation_transaction: Mapped[int] = mapped_column(
        BigInteger, server_default=text("txid_current()")
    )
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "statement_set_id", "mapping_digest"),
        source_fk("period_id", "accounting_periods"),
        source_fk("statement_set_id", "financial_statement_sets"),
        source_fk("balance_sheet_id", "financial_statements"),
        source_fk("income_statement_id", "financial_statements"),
        ForeignKeyConstraint(["generated_by"], ["users.id"], ondelete="RESTRICT"),
        CheckConstraint("method = 'INDIRECT' AND status = 'RECONCILED'", name="state"),
        CheckConstraint("close_version >= 1 AND policy_version >= 1", name="versions"),
        CheckConstraint(
            "opening_cash + net_operating + net_investing + net_financing + exchange_effect "
            "= closing_cash",
            name="reconciliation",
        ),
    )


class CashFlowEventModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_events"
    company_id: Mapped[UUID] = mapped_column(index=True)
    statement_id: Mapped[UUID]
    journal_id: Mapped[UUID]
    cash_line_id: Mapped[UUID]
    cash_account_id: Mapped[UUID]
    counterpart_line_id: Mapped[UUID]
    counterpart_account_id: Mapped[UUID]
    activity_type: Mapped[str] = mapped_column(String(20))
    line_code: Mapped[str] = mapped_column(String(40))
    cash_inflow: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    cash_outflow: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    classification_id: Mapped[UUID]
    classification_version: Mapped[int]
    evidence_id: Mapped[UUID | None]
    allocation_id: Mapped[UUID | None]
    allocation_version: Mapped[int | None]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "statement_id", "id"),
        UniqueConstraint("statement_id", "cash_line_id", "counterpart_line_id"),
        source_fk("statement_id", "cash_flow_statements"),
        source_fk("journal_id", "journal_entries"),
        source_fk("cash_account_id", "chart_of_accounts"),
        source_fk("counterpart_account_id", "chart_of_accounts"),
        source_fk("classification_id", "cash_flow_classifications"),
        source_fk("allocation_id", "cash_flow_allocations"),
        source_fk("evidence_id", "evidences"),
        ForeignKeyConstraint(
            ["company_id", "journal_id", "cash_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "journal_id", "counterpart_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(cash_inflow > 0 AND cash_outflow = 0) OR (cash_outflow > 0 AND cash_inflow = 0)",
            name="amount_side",
        ),
        CheckConstraint("classification_version >= 1", name="version"),
        CheckConstraint(
            "(allocation_id IS NULL AND allocation_version IS NULL) OR "
            "(allocation_id IS NOT NULL AND allocation_version IS NOT NULL "
            "AND allocation_version >= 1)",
            name="allocation",
        ),
    )


class CashFlowAdjustmentModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_adjustments"
    company_id: Mapped[UUID] = mapped_column(index=True)
    statement_id: Mapped[UUID]
    rule_id: Mapped[UUID]
    rule_version: Mapped[int]
    account_id: Mapped[UUID]
    adjustment_code: Mapped[str] = mapped_column(String(30))
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "statement_id", "id"),
        UniqueConstraint("statement_id", "account_id"),
        source_fk("statement_id", "cash_flow_statements"),
        source_fk("rule_id", "cash_flow_adjustment_rules"),
        source_fk("account_id", "chart_of_accounts"),
        CheckConstraint("rule_version >= 1", name="version"),
    )


class CashFlowAdjustmentSourceModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_adjustment_sources"
    company_id: Mapped[UUID] = mapped_column(index=True)
    adjustment_id: Mapped[UUID]
    journal_id: Mapped[UUID]
    journal_line_id: Mapped[UUID]
    entry_date: Mapped[date]
    signed_debit_amount: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    is_opening: Mapped[bool]
    __table_args__ = (
        UniqueConstraint("adjustment_id", "journal_line_id"),
        source_fk("adjustment_id", "cash_flow_adjustments"),
        ForeignKeyConstraint(
            ["company_id", "journal_id", "journal_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
    )


class CashFlowBalanceSourceModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_balance_sources"
    company_id: Mapped[UUID] = mapped_column(index=True)
    statement_id: Mapped[UUID]
    scope_id: Mapped[UUID]
    scope_version: Mapped[int]
    account_id: Mapped[UUID]
    journal_id: Mapped[UUID]
    journal_line_id: Mapped[UUID]
    entry_date: Mapped[date]
    signed_debit_amount: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    is_opening: Mapped[bool]
    __table_args__ = (
        UniqueConstraint("statement_id", "journal_line_id"),
        source_fk("statement_id", "cash_flow_statements"),
        source_fk("scope_id", "cash_scope_mappings"),
        source_fk("account_id", "chart_of_accounts"),
        ForeignKeyConstraint(
            ["company_id", "journal_id", "journal_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("scope_version >= 1", name="version"),
    )


class CashFlowLineModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_lines"
    company_id: Mapped[UUID] = mapped_column(index=True)
    statement_id: Mapped[UUID]
    line_code: Mapped[str] = mapped_column(String(60))
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    source_type: Mapped[str] = mapped_column(String(16))
    event_id: Mapped[UUID | None]
    adjustment_id: Mapped[UUID | None]
    display_order: Mapped[int]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("statement_id", "display_order"),
        source_fk("statement_id", "cash_flow_statements"),
        ForeignKeyConstraint(
            ["company_id", "statement_id", "event_id"],
            ["cash_flow_events.company_id", "cash_flow_events.statement_id", "cash_flow_events.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "statement_id", "adjustment_id"],
            [
                "cash_flow_adjustments.company_id",
                "cash_flow_adjustments.statement_id",
                "cash_flow_adjustments.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(source_type = 'EVENT' AND event_id IS NOT NULL AND adjustment_id IS NULL) OR "
            "(source_type = 'ADJUSTMENT' AND event_id IS NULL AND adjustment_id IS NOT NULL) OR "
            "(source_type IN ('TOTAL','NET_PROFIT') "
            "AND event_id IS NULL AND adjustment_id IS NULL)",
            name="source",
        ),
        CheckConstraint("display_order > 0", name="display_order"),
    )


class CashFlowJournalTraceModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_journal_traces"
    company_id: Mapped[UUID] = mapped_column(index=True)
    statement_id: Mapped[UUID]
    journal_id: Mapped[UUID]
    transaction_id: Mapped[UUID | None]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("statement_id", "journal_id"),
        source_fk("statement_id", "cash_flow_statements"),
        source_fk("journal_id", "journal_entries"),
        source_fk("transaction_id", "transactions"),
    )


class CashFlowEvidenceTraceModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_evidence_traces"
    company_id: Mapped[UUID] = mapped_column(index=True)
    journal_trace_id: Mapped[UUID]
    evidence_id: Mapped[UUID]
    __table_args__ = (
        UniqueConstraint("journal_trace_id", "evidence_id"),
        source_fk("journal_trace_id", "cash_flow_journal_traces"),
        source_fk("evidence_id", "evidences"),
    )


class CashFlowCommandModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_commands"
    company_id: Mapped[UUID] = mapped_column(index=True)
    actor_id: Mapped[UUID]
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    statement_id: Mapped[UUID]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "idempotency_key"),
        source_fk("statement_id", "cash_flow_statements"),
        ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
    )


class CashFlowStatementDisclosureModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_statement_disclosures"

    company_id: Mapped[UUID] = mapped_column(index=True)
    statement_id: Mapped[UUID]
    disclosure_id: Mapped[UUID]
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    source_type: Mapped[str] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("statement_id", "disclosure_id"),
        source_fk("statement_id", "cash_flow_statements"),
        source_fk("disclosure_id", "cash_flow_non_cash_disclosures"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )


class CashFlowStatementDisposalModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_statement_disposals"

    company_id: Mapped[UUID] = mapped_column(index=True)
    statement_id: Mapped[UUID]
    disposal_id: Mapped[UUID]
    proceeds: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    gain_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))

    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("statement_id", "disposal_id"),
        source_fk("statement_id", "cash_flow_statements"),
        source_fk("disposal_id", "cash_flow_disposal_sources"),
        CheckConstraint("proceeds > 0 AND gain_amount <> 0", name="amounts"),
    )
