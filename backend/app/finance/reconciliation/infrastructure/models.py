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
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        CheckConstraint("matched_amount > 0", name="amount"),
        CheckConstraint("status IN ('DRAFT','CONFIRMED')", name="status"),
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
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "reconciliation_match_id"],
            ["reconciliation_matches.company_id", "reconciliation_matches.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="amount"),
    )
