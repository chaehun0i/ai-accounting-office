"""현금 범위와 거래상대 계정의 활동 분류를 관계형으로 보존합니다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class CashFlowAdjustmentRuleModel(UUIDPrimaryKey, Base):
    __tablename__ = "cash_flow_adjustment_rules"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    account_id: Mapped[UUID]
    adjustment_code: Mapped[str] = mapped_column(String(30))
    source_mapping_type: Mapped[str] = mapped_column(String(30))
    related_account_id: Mapped[UUID | None]
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    version: Mapped[int]
    policy_code: Mapped[str] = mapped_column(String(40))
    policy_version: Mapped[int]
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
        ForeignKeyConstraint(
            ["company_id", "related_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1 AND policy_version >= 1", name="versions"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="dates"),
        CheckConstraint(
            "adjustment_code IN ('OPERATING_RESULT','NONCASH_PAIR',"
            "'WORKING_CAPITAL','EXCLUDED_BALANCE')",
            name="adjustment_code",
        ),
        CheckConstraint(
            "source_mapping_type IN ('ACCOUNT_LEDGER','ASSET_REGISTER','INVENTORY_SUBLEDGER')",
            name="source_mapping_type",
        ),
        CheckConstraint(
            "(adjustment_code = 'NONCASH_PAIR' AND related_account_id IS NOT NULL "
            "AND related_account_id <> account_id) OR "
            "(adjustment_code <> 'NONCASH_PAIR' AND related_account_id IS NULL)",
            name="related_account",
        ),
    )


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


class CashFlowAllocationModel(UUIDPrimaryKey, Base):
    """Evidence-backed pairing for a cash leg in a complex posted journal."""

    __tablename__ = "cash_flow_allocations"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    journal_id: Mapped[UUID]
    cash_line_id: Mapped[UUID]
    counterpart_line_id: Mapped[UUID]
    evidence_id: Mapped[UUID]
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    version: Mapped[int]
    replaces_id: Mapped[UUID | None]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]

    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint(
            "company_id", "journal_id", "cash_line_id", "counterpart_line_id", "version"
        ),
        UniqueConstraint("company_id", "replaces_id"),
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "journal_id", "cash_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "journal_id", "counterpart_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "replaces_id"],
            ["cash_flow_allocations.company_id", "cash_flow_allocations.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("cash_line_id <> counterpart_line_id", name="distinct_lines"),
    )
