"""Versioned company choices and evidence-backed noncash ledger pairings."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class CashPolicyModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_policies"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    effective_from: Mapped[date]
    interest_paid: Mapped[str] = mapped_column(String(12))
    interest_received: Mapped[str] = mapped_column(String(12))
    tax_paid: Mapped[str] = mapped_column(String(12))
    version: Mapped[int]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "version"),
        UniqueConstraint("company_id", "effective_from"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("interest_paid IN ('OPERATING','FINANCING')", name="interest_paid"),
        CheckConstraint("interest_received IN ('OPERATING','INVESTING')", name="interest_received"),
        CheckConstraint("tax_paid IN ('OPERATING','INVESTING','FINANCING')", name="tax_paid"),
    )


class NoncashDisclosureModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_noncash_disclosures"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    journal_id: Mapped[UUID]
    debit_line_id: Mapped[UUID]
    credit_line_id: Mapped[UUID]
    evidence_id: Mapped[UUID]
    transaction_type: Mapped[str] = mapped_column(String(24))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "journal_id", "debit_line_id", "credit_line_id"),
        ForeignKeyConstraint(
            ["company_id", "journal_id", "debit_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "journal_id", "credit_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_id"], ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("debit_line_id <> credit_line_id", name="lines"),
        CheckConstraint(
            "transaction_type IN ('LEASE_ACQUISITION','IN_KIND_CAPITAL','DEBT_TO_EQUITY')",
            name="transaction_type",
        ),
    )


class FrozenNoncashModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_snapshot_noncash"
    company_id: Mapped[UUID]
    statement_id: Mapped[UUID]
    disclosure_id: Mapped[UUID]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("statement_id", "disclosure_id"),
        ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["cash_flow_statements.company_id", "cash_flow_statements.id"], ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "disclosure_id"],
            ["cash_flow_noncash_disclosures.company_id", "cash_flow_noncash_disclosures.id"],
            ondelete="RESTRICT",
        ),
    )
