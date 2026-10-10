from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class OpeningImportModel(UUIDPrimaryKey, Base):
    __tablename__ = "opening_balance_imports"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    onboarding_session_id: Mapped[UUID] = mapped_column(index=True)
    source_version: Mapped[int]
    source_digest: Mapped[str] = mapped_column(String(64))
    as_of_date: Mapped[date]
    journal_id: Mapped[UUID] = mapped_column(index=True, unique=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "onboarding_session_id", "source_version"),
        UniqueConstraint("company_id", "onboarding_session_id"),
        ForeignKeyConstraint(
            ["company_id", "onboarding_session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("source_version>=1", name="version"),
    )


class OpeningLineModel(UUIDPrimaryKey, Base):
    __tablename__ = "opening_balance_lines"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    opening_balance_import_id: Mapped[UUID] = mapped_column(index=True)
    source_row_key: Mapped[str] = mapped_column(String(300))
    account_id: Mapped[UUID] = mapped_column(index=True)
    counterparty_id: Mapped[UUID | None] = mapped_column(index=True)
    debit_amount: Mapped[Decimal]
    credit_amount: Mapped[Decimal]
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "opening_balance_import_id"],
            ["opening_balance_imports.company_id", "opening_balance_imports.id"],
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
        CheckConstraint(
            "(debit_amount>0 AND credit_amount=0) OR (credit_amount>0 AND debit_amount=0)",
            name="amount_side",
        ),
    )
