"""회사 복합 외래키와 금액 제약을 갖는 관계형 재무 보조부입니다."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class ReconciliationMatchModel(UUIDPrimaryKey, Base):
    __tablename__ = "reconciliation_matches"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    match_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    matched_amount: Mapped[Decimal]
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime]
    version: Mapped[int] = mapped_column(server_default="1")
    confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    confirmed_at: Mapped[datetime | None]
    unmatched_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    unmatched_at: Mapped[datetime | None]
    unmatch_reason: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        CheckConstraint("matched_amount > 0 AND matched_amount < 1000000000000000", name="amount"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("status IN ('DRAFT','CONFIRMED','UNMATCHED')", name="status"),
    )


class ReconciliationMatchLineModel(UUIDPrimaryKey, Base):
    __tablename__ = "reconciliation_match_lines"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    reconciliation_match_id: Mapped[UUID] = mapped_column(index=True)
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[UUID]
    target_type: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[UUID]
    amount: Mapped[Decimal]
    source_version: Mapped[int] = mapped_column(server_default="1")
    target_version: Mapped[int] = mapped_column(server_default="1")
    bank_transaction_id: Mapped[UUID | None] = mapped_column(index=True)
    card_transaction_id: Mapped[UUID | None] = mapped_column(index=True)
    collection_id: Mapped[UUID | None] = mapped_column(index=True)
    payment_id: Mapped[UUID | None] = mapped_column(index=True)
    transaction_id: Mapped[UUID | None] = mapped_column(index=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "bank_transaction_id"],
            ["bank_transactions.company_id", "bank_transactions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "card_transaction_id"],
            ["card_transactions.company_id", "card_transactions.id"],
            ondelete="RESTRICT",
        ),
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
        ForeignKeyConstraint(
            ["company_id", "transaction_id"],
            ["transactions.company_id", "transactions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("source_version >= 1 AND target_version >= 1", name="versions"),
        CheckConstraint(
            "num_nonnulls(bank_transaction_id,card_transaction_id) = 1 AND "
            "num_nonnulls(collection_id,payment_id,transaction_id) = 1",
            name="typed_references",
        ),
        CheckConstraint(
            "(source_type = 'BANK' AND source_id = bank_transaction_id AND "
            "bank_transaction_id IS NOT NULL) OR (source_type = 'CARD' AND source_id = "
            "card_transaction_id AND card_transaction_id IS NOT NULL)",
            name="source_identity",
        ),
        CheckConstraint(
            "(target_type = 'COLLECTION' AND target_id = collection_id AND "
            "collection_id IS NOT NULL) OR (target_type = 'PAYMENT' AND target_id = "
            "payment_id AND payment_id IS NOT NULL) OR (target_type = 'TRANSACTION' AND "
            "target_id = transaction_id AND transaction_id IS NOT NULL)",
            name="target_identity",
        ),
        ForeignKeyConstraint(
            ["company_id", "reconciliation_match_id"],
            ["reconciliation_matches.company_id", "reconciliation_matches.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="amount"),
    )
