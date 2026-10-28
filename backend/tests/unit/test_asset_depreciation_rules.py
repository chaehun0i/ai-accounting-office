"""Fixed asset amounts are calculated deterministically without posting a Journal."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.accounting.journals.domain.errors import AccountingError
from app.assets.domain.entities import AssetPolicy, FixedAsset
from app.assets.domain.rules import cumulative_depreciation


def sample() -> tuple[FixedAsset, AssetPolicy]:
    company, actor = uuid4(), uuid4()
    asset = FixedAsset(
        id=uuid4(),
        company_id=company,
        asset_code="A-1",
        asset_name="설비",
        asset_class="EQUIPMENT",
        acquisition_date=date(2026, 1, 15),
        in_service_date=date(2026, 1, 15),
        acquisition_cost=Decimal("1200.0000"),
        residual_value=Decimal("0.0000"),
        useful_life_months=12,
        depreciation_method="STRAIGHT_LINE",
        status="IN_SERVICE",
        asset_account_id=uuid4(),
        accumulated_account_id=uuid4(),
        expense_account_id=uuid4(),
        acquisition_journal_id=uuid4(),
        version=1,
        created_by=actor,
        created_at=datetime(2026, 1, 15, tzinfo=UTC),
    )
    policy = AssetPolicy(
        id=uuid4(),
        company_id=company,
        version=1,
        effective_from=date(2026, 1, 1),
        proration="MONTHLY",
        acquisition_month="FULL",
        created_by=actor,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return asset, policy


def test_monthly_depreciation_caps_at_cost_less_residual():
    asset, policy = sample()
    assert cumulative_depreciation(asset, policy, date(2026, 1, 31)) == Decimal("100.0000")
    assert cumulative_depreciation(asset, policy, date(2026, 12, 31)) == Decimal("1200.0000")
    assert cumulative_depreciation(asset, policy, date(2027, 12, 31)) == Decimal("1200.0000")


def test_next_month_and_daily_proration():
    asset, policy = sample()
    next_month = replace(policy, acquisition_month="NEXT_MONTH")
    assert cumulative_depreciation(asset, next_month, date(2026, 1, 31)) == 0
    assert cumulative_depreciation(asset, next_month, date(2026, 2, 28)) == Decimal("100.0000")
    daily = replace(policy, proration="DAILY")
    assert cumulative_depreciation(asset, daily, date(2026, 1, 31)) == Decimal("54.8387")
    assert cumulative_depreciation(asset, daily, date(2027, 1, 31)) == Decimal("1200.0000")


def test_invalid_account_roles_and_non_month_end_are_rejected():
    asset, policy = sample()
    with pytest.raises(AccountingError):
        cumulative_depreciation(
            replace(asset, expense_account_id=asset.asset_account_id), policy, date(2026, 1, 31)
        )
    with pytest.raises(AccountingError):
        cumulative_depreciation(asset, policy, date(2026, 1, 30))
