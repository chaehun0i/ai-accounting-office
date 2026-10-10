"""전표와 분개는 회사 복합 FK 및 금액 CHECK를 사용합니다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class JournalModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "journal_entries"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    accounting_period_id: Mapped[UUID] = mapped_column(index=True)
    source_transaction_id: Mapped[UUID | None] = mapped_column(index=True)
    entry_date: Mapped[date] = mapped_column(index=True)
    description: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(30))
    proposal_origin: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), index=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    journal_no: Mapped[str | None] = mapped_column(String(80))
    reversal_of_id: Mapped[UUID | None] = mapped_column(index=True)
    approved_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    approved_at: Mapped[datetime | None]
    approval_id: Mapped[UUID | None] = mapped_column(index=True)
    posted_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    posted_at: Mapped[datetime | None]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        ForeignKeyConstraint(
            ["company_id", "approval_id"],
            ["approvals.company_id", "approvals.id"],
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_journal_approval",
        ),
        UniqueConstraint("company_id", "journal_no"),
        UniqueConstraint("company_id", "reversal_of_id"),
        ForeignKeyConstraint(
            ["company_id", "accounting_period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "source_transaction_id"],
            ["transactions.company_id", "transactions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "reversal_of_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PROPOSED','REVIEW_REQUIRED','APPROVED','REJECTED','POSTED')",
            name="status",
        ),
        CheckConstraint(
            "source_type IN ('MANUAL','TRANSACTION','OPENING','REVERSAL')", name="source"
        ),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "(status='POSTED' AND journal_no IS NOT NULL AND posted_at IS NOT NULL AND posted_by IS NOT NULL "
            "AND approval_id IS NOT NULL) "
            "OR (status<>'POSTED' AND journal_no IS NULL AND posted_at IS NULL)",
            name="posted",
        ),
        CheckConstraint("reversal_of_id IS NULL OR reversal_of_id <> id", name="reversal"),
    )


class JournalLineModel(UUIDPrimaryKey, Base):
    __tablename__ = "journal_lines"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    journal_entry_id: Mapped[UUID] = mapped_column(index=True)
    line_no: Mapped[int]
    account_id: Mapped[UUID] = mapped_column(index=True)
    counterparty_id: Mapped[UUID | None] = mapped_column(index=True)
    debit_amount: Mapped[Decimal]
    credit_amount: Mapped[Decimal]
    memo: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("journal_entry_id", "line_no"),
        ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "counterparty_id"],
            ["counterparties.company_id", "counterparties.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("line_no > 0", name="line_no"),
        CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0)",
            name="amount_side",
        ),
    )


class JournalEvidenceModel(UUIDPrimaryKey, Base):
    __tablename__ = "journal_evidences"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    journal_entry_id: Mapped[UUID] = mapped_column(index=True)
    evidence_id: Mapped[UUID] = mapped_column(index=True)
    __table_args__ = (
        UniqueConstraint("journal_entry_id", "evidence_id"),
        ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
    )


class JournalProposalModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "journal_proposals"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    journal_entry_id: Mapped[UUID] = mapped_column(index=True, unique=True)
    transaction_id: Mapped[UUID | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(30))
    reason_summary: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "transaction_id"],
            ["transactions.company_id", "transactions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="version"),
    )
