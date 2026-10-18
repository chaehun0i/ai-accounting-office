from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class ControlAccountMappingModel(UUIDPrimaryKey, Base):
    __tablename__ = "control_account_mappings"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    role: Mapped[str] = mapped_column(String(24))
    account_id: Mapped[UUID] = mapped_column()
    version: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("company_id", "role"),
        UniqueConstraint("company_id", "account_id"),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "role IN ('AR','AP','TAX_INPUT','TAX_OUTPUT',"
            "'BANK_CASH','CARD_CLEARING','CARD_PAYABLE')",
            name="role",
        ),
        CheckConstraint("version >= 1", name="version"),
    )


class ControlAccountRequestModel(UUIDPrimaryKey, Base):
    __tablename__ = "control_account_requests"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    role: Mapped[str] = mapped_column(String(24))
    current_account_id: Mapped[UUID | None] = mapped_column()
    target_account_id: Mapped[UUID] = mapped_column()
    expected_mapping_version: Mapped[int]
    expected_target_account_version: Mapped[int]
    impact_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    requester_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    request_key: Mapped[str] = mapped_column(String(100))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    approver_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_key: Mapped[str | None] = mapped_column(String(100))
    execution_fingerprint: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("company_id", "requester_id", "request_key"),
        Index(
            "uq_control_account_execution_key",
            "company_id",
            "executed_by_id",
            "execution_key",
            unique=True,
            postgresql_where=text("execution_key IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["company_id", "current_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "target_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "role IN ('AR','AP','TAX_INPUT','TAX_OUTPUT',"
            "'BANK_CASH','CARD_CLEARING','CARD_PAYABLE')",
            name="role",
        ),
        CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED','EXECUTED')", name="status"),
        CheckConstraint(
            "expected_mapping_version >= 0 AND expected_target_account_version >= 1 "
            "AND version >= 1",
            name="versions",
        ),
        Index("ix_control_account_requests_company_created", "company_id", "created_at"),
    )


class ControlAccountEventModel(UUIDPrimaryKey, Base):
    __tablename__ = "control_account_events"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_account_requests.id", ondelete="RESTRICT")
    )
    role: Mapped[str] = mapped_column(String(24))
    event_type: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(500))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    before_account_id: Mapped[UUID | None] = mapped_column()
    after_account_id: Mapped[UUID | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "before_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "after_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_control_account_events_company_request", "company_id", "request_id", "occurred_at"
        ),
    )
