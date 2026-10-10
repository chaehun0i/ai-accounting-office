from datetime import datetime
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
from app.core.database.mixins import UUIDPrimaryKey


class ApprovalModel(UUIDPrimaryKey, Base):
    __tablename__ = "approvals"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    journal_id: Mapped[UUID] = mapped_column(index=True)
    target_version: Mapped[int]
    target_digest: Mapped[str] = mapped_column(String(64))
    action_code: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    requester_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    reviewer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    requested_at: Mapped[datetime]
    decided_at: Mapped[datetime | None]
    expires_at: Mapped[datetime]
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','CONSUMED','EXPIRED')", name="status"
        ),
        CheckConstraint("target_version>=1", name="version"),
        CheckConstraint("reviewer_id IS NULL OR reviewer_id<>requester_id", name="separation"),
    )


class AuditEventModel(UUIDPrimaryKey, Base):
    __tablename__ = "audit_events"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    journal_id: Mapped[UUID] = mapped_column(index=True)
    action_code: Mapped[str] = mapped_column(String(40))
    result_code: Mapped[str] = mapped_column(String(20))
    request_id: Mapped[str] = mapped_column(String(100))
    before_digest: Mapped[str] = mapped_column(String(64))
    after_digest: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime]
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
    )


class IdempotencyModel(UUIDPrimaryKey, Base):
    __tablename__ = "idempotency_records"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    command_code: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    journal_id: Mapped[UUID] = mapped_column(index=True)
    result_version: Mapped[int]
    http_status: Mapped[int]
    created_at: Mapped[datetime]
    completed_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "command_code", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status='SUCCEEDED'", name="status"),
    )
