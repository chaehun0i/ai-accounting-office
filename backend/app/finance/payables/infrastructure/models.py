"""회사 복합 외래키와 금액 제약을 갖는 관계형 재무 보조부입니다."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class PayableModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "payables"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    counterparty_id: Mapped[UUID] = mapped_column(index=True)
    origin_journal_id: Mapped[UUID | None] = mapped_column(index=True)
    origin_line_no: Mapped[int | None]
    source_transaction_id: Mapped[UUID | None] = mapped_column(index=True)
    source_invoice_id: Mapped[UUID | None] = mapped_column(index=True)
    recognized_date: Mapped[date | None]
    account_id: Mapped[UUID] = mapped_column(index=True)
    original_amount: Mapped[Decimal]
    outstanding_amount: Mapped[Decimal]
    currency_code: Mapped[str] = mapped_column(String(3))
    due_date: Mapped[date] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "origin_journal_id", "origin_line_no"),
        UniqueConstraint("company_id", "source_invoice_id"),
        UniqueConstraint("company_id", "source_transaction_id"),
        ForeignKeyConstraint(
            ["company_id", "source_invoice_id"],
            ["purchase_invoices.company_id", "purchase_invoices.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "source_transaction_id"],
            ["transactions.company_id", "transactions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(origin_journal_id IS NOT NULL AND origin_line_no IS NOT NULL) OR "
            "(source_invoice_id IS NOT NULL AND source_transaction_id IS NOT NULL "
            "AND recognized_date IS NOT NULL)",
            name="source",
        ),
        ForeignKeyConstraint(
            ["company_id", "counterparty_id"],
            ["counterparties.company_id", "counterparties.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "origin_journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["origin_journal_id", "origin_line_no"],
            ["journal_lines.journal_entry_id", "journal_lines.line_no"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "original_amount > 0 AND outstanding_amount >= 0",
            name="amount",
        ),
        CheckConstraint("currency_code='KRW'", name="currency"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "status IN ('OPEN','PARTIAL','SETTLED','CANCELLED','WRITEOFF')", name="status"
        ),
    )
