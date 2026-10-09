from datetime import date
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
from app.core.database.mixins import UUIDPrimaryKey


class COATemplateModel(UUIDPrimaryKey, Base):
    __tablename__ = "coa_templates"
    template_code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(16))
    valid_from: Mapped[date]
    __table_args__ = (
        UniqueConstraint("template_code", "version"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name="status"),
    )


class COATemplateAccountModel(UUIDPrimaryKey, Base):
    __tablename__ = "coa_template_accounts"
    coa_template_id: Mapped[UUID] = mapped_column(
        ForeignKey("coa_templates.id", ondelete="RESTRICT"), index=True
    )
    account_code: Mapped[str] = mapped_column(String(20))
    account_name: Mapped[str] = mapped_column(String(200))
    account_type: Mapped[str] = mapped_column(String(16))
    normal_balance: Mapped[str] = mapped_column(String(6))
    parent_code: Mapped[str | None] = mapped_column(String(20))
    posting_allowed: Mapped[bool]
    display_order: Mapped[int]
    is_contra: Mapped[bool] = mapped_column(server_default=text("false"))
    __table_args__ = (
        UniqueConstraint("coa_template_id", "account_code"),
        ForeignKeyConstraint(
            ["coa_template_id", "parent_code"],
            ["coa_template_accounts.coa_template_id", "coa_template_accounts.account_code"],
            ondelete="RESTRICT",
        ),
        Index("ix_coa_template_accounts_parent", "coa_template_id", "parent_code"),
        CheckConstraint(
            "parent_code IS NULL OR parent_code <> account_code", name="parent_not_self"
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
        CheckConstraint("display_order >= 0", name="display_order"),
    )
