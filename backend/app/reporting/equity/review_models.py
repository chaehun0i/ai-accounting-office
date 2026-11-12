from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class EquityReviewModel(UUIDPrimaryKey, Base):
    __tablename__ = "equity_review_events"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    statement_id: Mapped[UUID]
    source_digest: Mapped[str] = mapped_column(String(64))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(String(1000))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "statement_id", "version"),
        UniqueConstraint("company_id", "actor_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["statement_of_changes_in_equity.company_id", "statement_of_changes_in_equity.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0 AND length(trim(reason)) > 0", name="input"),
        CheckConstraint("status IN ('REVIEW_REQUESTED','APPROVED','REJECTED')", name="status"),
        CheckConstraint(
            "status = 'REVIEW_REQUESTED' OR actor_id <> requested_by", name="separation"
        ),
    )
