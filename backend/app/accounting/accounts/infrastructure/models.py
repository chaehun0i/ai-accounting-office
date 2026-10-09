from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class AccountModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "chart_of_accounts"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    template_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("coa_template_accounts.id", ondelete="RESTRICT"), index=True
    )
    account_code: Mapped[str] = mapped_column(String(20))
    account_name: Mapped[str] = mapped_column(String(200))
    account_type: Mapped[str] = mapped_column(String(16))
    normal_balance: Mapped[str] = mapped_column(String(6))
    parent_account_id: Mapped[UUID | None] = mapped_column(index=True)
    posting_allowed: Mapped[bool]
    is_contra: Mapped[bool] = mapped_column(server_default=text("false"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'ACTIVE'"))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "account_code"),
        ForeignKeyConstraint(
            ["company_id", "parent_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_chart_of_accounts_parent", "company_id", "parent_account_id"),
        CheckConstraint(
            "parent_account_id IS NULL OR parent_account_id <> id", name="parent_not_self"
        ),
        CheckConstraint(
            "account_type IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')", name="type"
        ),
        CheckConstraint("normal_balance IN ('DEBIT','CREDIT')", name="balance_side"),
        CheckConstraint(
            "normal_balance = CASE WHEN (account_type IN ('ASSET','EXPENSE')) "
            "<> is_contra THEN 'DEBIT' ELSE 'CREDIT' END",
            name="normal_balance",
        ),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("version >= 1", name="version"),
    )
