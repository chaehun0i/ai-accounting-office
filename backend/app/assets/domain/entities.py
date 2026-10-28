from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class AssetPolicy:
    id: UUID
    company_id: UUID
    version: int
    effective_from: date
    proration: str
    acquisition_month: str
    created_by: UUID
    created_at: datetime


@dataclass(frozen=True, kw_only=True)
class FixedAsset:
    id: UUID
    company_id: UUID
    asset_code: str
    asset_name: str
    asset_class: str
    acquisition_date: date
    in_service_date: date
    acquisition_cost: Decimal
    residual_value: Decimal
    useful_life_months: int
    depreciation_method: str
    status: str
    asset_account_id: UUID
    accumulated_account_id: UUID
    expense_account_id: UUID
    acquisition_journal_id: UUID
    version: int
    created_by: UUID
    created_at: datetime


@dataclass(frozen=True, kw_only=True)
class DepreciationLine:
    id: UUID
    company_id: UUID
    depreciation_run_id: UUID
    fixed_asset_id: UUID
    opening_accumulated: Decimal
    current_depreciation: Decimal
    closing_accumulated: Decimal
    carrying_amount: Decimal
    proposed_journal_id: UUID | None


@dataclass(frozen=True, kw_only=True)
class DepreciationRun:
    id: UUID
    company_id: UUID
    period_id: UUID
    policy_id: UUID
    policy_version: int
    status: str
    total_amount: Decimal
    created_by: UUID
    created_at: datetime
    lines: tuple[DepreciationLine, ...]
