"""회사 복합 외래키와 금액 제약을 갖는 관계형 재무 보조부입니다."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class ReceivableModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "receivables"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    counterparty_id: Mapped[UUID] = mapped_column(index=True)
    origin_journal_id: Mapped[UUID] = mapped_column(index=True)
    origin_line_no: Mapped[int]
    account_id: Mapped[UUID] = mapped_column(index=True)
    original_amount: Mapped[Decimal]
    outstanding_amount: Mapped[Decimal]
    currency_code: Mapped[str] = mapped_column(String(3))
    due_date: Mapped[date] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "origin_journal_id", "origin_line_no"),
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
            "original_amount > 0 AND outstanding_amount >= 0 "
            "AND outstanding_amount <= original_amount",
            name="amount",
        ),
        CheckConstraint("currency_code='KRW'", name="currency"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("status IN ('OPEN','PARTIAL','SETTLED','WRITEOFF')", name="status"),
    )
