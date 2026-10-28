from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class AssetPolicyModel(UUIDPrimaryKey, Base):
    __tablename__ = "fixed_asset_policies"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    version: Mapped[int]
    effective_from: Mapped[date]
    proration: Mapped[str] = mapped_column(String(20))
    acquisition_month: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id", "version"),
        UniqueConstraint("company_id", "version"),
        UniqueConstraint("company_id", "effective_from"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("proration IN ('MONTHLY','DAILY')", name="proration"),
        CheckConstraint("acquisition_month IN ('FULL','NEXT_MONTH')", name="acquisition_month"),
        CheckConstraint("extract(day from effective_from)=1", name="effective_from"),
    )


class FixedAssetModel(UUIDPrimaryKey, Base):
    __tablename__ = "fixed_assets"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    asset_code: Mapped[str] = mapped_column(String(40))
    asset_name: Mapped[str] = mapped_column(String(200))
    asset_class: Mapped[str] = mapped_column(String(60))
    acquisition_date: Mapped[date]
    in_service_date: Mapped[date]
    acquisition_cost: Mapped[Decimal]
    residual_value: Mapped[Decimal]
    useful_life_months: Mapped[int]
    depreciation_method: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    asset_account_id: Mapped[UUID]
    accumulated_account_id: Mapped[UUID]
    expense_account_id: Mapped[UUID]
    acquisition_journal_id: Mapped[UUID]
    version: Mapped[int]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "asset_code"),
        UniqueConstraint("company_id", "acquisition_journal_id"),
        ForeignKeyConstraint(["company_id", "acquisition_journal_id"],
                             ["journal_entries.company_id", "journal_entries.id"], ondelete="RESTRICT"),
        *(ForeignKeyConstraint(["company_id", field],
                               ["chart_of_accounts.company_id", "chart_of_accounts.id"], ondelete="RESTRICT")
          for field in ("asset_account_id", "accumulated_account_id", "expense_account_id")),
        CheckConstraint("acquisition_cost > 0 AND residual_value >= 0 AND residual_value <= acquisition_cost", name="amounts"),
        CheckConstraint("useful_life_months BETWEEN 1 AND 1200", name="life"),
        CheckConstraint("in_service_date >= acquisition_date", name="dates"),
        CheckConstraint("depreciation_method='STRAIGHT_LINE' AND status='IN_SERVICE' AND version=1", name="state"),
        CheckConstraint("asset_account_id <> accumulated_account_id AND asset_account_id <> expense_account_id AND accumulated_account_id <> expense_account_id", name="accounts"),
        CheckConstraint("asset_code ~ '^[A-Z0-9][A-Z0-9_-]{0,39}$'", name="code"),
    )


class DepreciationRunModel(UUIDPrimaryKey, Base):
    __tablename__ = "depreciation_runs"
    company_id: Mapped[UUID]
    period_id: Mapped[UUID]
    policy_id: Mapped[UUID]
    policy_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))
    total_amount: Mapped[Decimal]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "period_id"),
        ForeignKeyConstraint(["company_id", "period_id"],
                             ["accounting_periods.company_id", "accounting_periods.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["company_id", "policy_id", "policy_version"],
                             ["fixed_asset_policies.company_id", "fixed_asset_policies.id", "fixed_asset_policies.version"], ondelete="RESTRICT"),
        CheckConstraint("status='CALCULATED' AND total_amount >= 0", name="state"),
    )


class DepreciationLineModel(UUIDPrimaryKey, Base):
    __tablename__ = "depreciation_lines"
    company_id: Mapped[UUID]
    depreciation_run_id: Mapped[UUID]
    fixed_asset_id: Mapped[UUID]
    opening_accumulated: Mapped[Decimal]
    current_depreciation: Mapped[Decimal]
    closing_accumulated: Mapped[Decimal]
    carrying_amount: Mapped[Decimal]
    proposed_journal_id: Mapped[UUID | None]
    __table_args__ = (
        UniqueConstraint("depreciation_run_id", "fixed_asset_id"),
        UniqueConstraint("proposed_journal_id"),
        ForeignKeyConstraint(["company_id", "depreciation_run_id"],
                             ["depreciation_runs.company_id", "depreciation_runs.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["company_id", "fixed_asset_id"],
                             ["fixed_assets.company_id", "fixed_assets.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["company_id", "proposed_journal_id"],
                             ["journal_entries.company_id", "journal_entries.id"], ondelete="RESTRICT"),
        CheckConstraint("opening_accumulated >= 0 AND current_depreciation >= 0 AND carrying_amount >= 0", name="amounts"),
        CheckConstraint("closing_accumulated=opening_accumulated+current_depreciation", name="bridge"),
        CheckConstraint("(current_depreciation=0 AND proposed_journal_id IS NULL) OR (current_depreciation>0 AND proposed_journal_id IS NOT NULL)", name="journal"),
    )
