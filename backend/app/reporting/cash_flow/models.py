"""현금 범위와 거래상대 계정의 활동 분류를 관계형으로 보존합니다."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class CashScopeMappingModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_scope_mappings"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    account_id: Mapped[UUID]
    scope_type: Mapped[str] = mapped_column(String(20))
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    status: Mapped[str] = mapped_column(String(12), server_default=text("'ACTIVE'"))
    version: Mapped[int] = mapped_column(server_default=text("1"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]

    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "account_id"),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("scope_type IN ('CASH','CASH_EQUIVALENT')", name="scope_type"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="dates"),
        CheckConstraint("version >= 1", name="version"),
    )


class CashFlowClassificationModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_classifications"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    account_id: Mapped[UUID]
    activity_type: Mapped[str] = mapped_column(String(20))
    line_code: Mapped[str] = mapped_column(String(40))
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    status: Mapped[str] = mapped_column(String(12), server_default=text("'ACTIVE'"))
    version: Mapped[int] = mapped_column(server_default=text("1"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]

    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "account_id"),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "activity_type IN ('OPERATING','INVESTING','FINANCING','EXCHANGE_EFFECT')",
            name="activity_type",
        ),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="dates"),
        CheckConstraint("version >= 1", name="version"),
    )
