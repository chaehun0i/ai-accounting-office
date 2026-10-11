"""회사 복합 외래키와 금액 제약을 갖는 관계형 재무 보조부입니다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class CollectionModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "collections"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    journal_entry_id: Mapped[UUID] = mapped_column(index=True)
    received_date: Mapped[date] = mapped_column(index=True)
    total_amount: Mapped[Decimal]
    currency_code: Mapped[str] = mapped_column(String(3))
    method: Mapped[str] = mapped_column(String(20))
    reference_no: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    confirmed_at: Mapped[datetime | None]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "journal_entry_id"),
        ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("total_amount > 0", name="amount"),
        CheckConstraint("currency_code='KRW'", name="currency"),
        CheckConstraint("method IN ('BANK_TRANSFER','CASH','OTHER')", name="method"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("status IN ('DRAFT','CONFIRMED','UNAPPLIED')", name="status"),
        CheckConstraint(
            "(status='DRAFT' AND confirmed_at IS NULL) "
            "OR (status<>'DRAFT' AND confirmed_at IS NOT NULL)",
            name="confirmed",
        ),
    )


class PaymentModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "payments"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    journal_entry_id: Mapped[UUID] = mapped_column(index=True)
    payment_date: Mapped[date] = mapped_column(index=True)
    total_amount: Mapped[Decimal]
    currency_code: Mapped[str] = mapped_column(String(3))
    method: Mapped[str] = mapped_column(String(20))
    reference_no: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    confirmed_at: Mapped[datetime | None]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "journal_entry_id"),
        ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("total_amount > 0", name="amount"),
        CheckConstraint("currency_code='KRW'", name="currency"),
        CheckConstraint("method IN ('BANK_TRANSFER','CASH','OTHER')", name="method"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("status IN ('DRAFT','CONFIRMED','UNAPPLIED')", name="status"),
        CheckConstraint(
            "(status='DRAFT' AND confirmed_at IS NULL) "
            "OR (status<>'DRAFT' AND confirmed_at IS NOT NULL)",
            name="confirmed",
        ),
    )


class CollectionAllocationModel(UUIDPrimaryKey, Base):
    __tablename__ = "collection_allocations"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    collection_id: Mapped[UUID] = mapped_column(index=True)
    receivable_id: Mapped[UUID] = mapped_column(index=True)
    allocated_amount: Mapped[Decimal]
    expected_version: Mapped[int]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("collection_id", "receivable_id"),
        ForeignKeyConstraint(
            ["company_id", "collection_id"],
            ["collections.company_id", "collections.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "receivable_id"],
            ["receivables.company_id", "receivables.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("allocated_amount > 0", name="amount"),
        CheckConstraint("expected_version >= 1", name="version"),
    )


class PaymentAllocationModel(UUIDPrimaryKey, Base):
    __tablename__ = "payment_allocations"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    payment_id: Mapped[UUID] = mapped_column(index=True)
    payable_id: Mapped[UUID] = mapped_column(index=True)
    allocated_amount: Mapped[Decimal]
    expected_version: Mapped[int]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("payment_id", "payable_id"),
        ForeignKeyConstraint(
            ["company_id", "payment_id"],
            ["payments.company_id", "payments.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "payable_id"],
            ["payables.company_id", "payables.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("allocated_amount > 0", name="amount"),
        CheckConstraint("expected_version >= 1", name="version"),
    )


class FinanceReceiptModel(UUIDPrimaryKey, Base):
    __tablename__ = "finance_command_receipts"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    command_code: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    collection_id: Mapped[UUID | None] = mapped_column(index=True)
    payment_id: Mapped[UUID | None] = mapped_column(index=True)
    result_version: Mapped[int]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "command_code", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "collection_id"],
            ["collections.company_id", "collections.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "payment_id"],
            ["payments.company_id", "payments.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("(collection_id IS NULL) <> (payment_id IS NULL)", name="resource"),
    )
