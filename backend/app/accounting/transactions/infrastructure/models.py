"""회사 복합 외래키로 원천 연결의 회사 경계를 보장합니다."""

from datetime import date
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


class TransactionModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "transactions"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    transaction_date: Mapped[date] = mapped_column(index=True)
    accounting_date: Mapped[date]
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal]
    tax_amount: Mapped[Decimal]
    currency_code: Mapped[str] = mapped_column(String(3))
    direction: Mapped[str] = mapped_column(String(12))
    source_type: Mapped[str] = mapped_column(String(30))
    source_system: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str] = mapped_column(String(100))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    payment_method: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), index=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    counterparty_id: Mapped[UUID | None] = mapped_column(index=True)
    import_id: Mapped[UUID | None] = mapped_column(index=True)
    evidence_id: Mapped[UUID | None] = mapped_column(index=True)
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "source_system", "source_id"),
        ForeignKeyConstraint(
            ["company_id", "counterparty_id"],
            ["counterparties.company_id", "counterparties.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "import_id"], ["imports.company_id", "imports.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0 AND tax_amount >= 0 AND tax_amount <= amount", name="amount"),
        CheckConstraint("direction IN ('INFLOW','OUTFLOW')", name="direction"),
        CheckConstraint("currency_code = 'KRW'", name="currency"),
        CheckConstraint(
            "status IN ('RECEIVED','NORMALIZED','READY_FOR_ACCOUNTING',"
            "'NEEDS_INFORMATION','DUPLICATE_REVIEW','EXCLUDED')",
            name="status",
        ),
        CheckConstraint("version >= 1", name="version"),
    )
