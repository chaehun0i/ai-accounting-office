"""Explicit accounting policies and Decimal-only straight-line calculations."""

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.accounting.journals.domain.errors import AccountingError
from app.assets.domain.entities import AssetPolicy, FixedAsset
from app.core.values import MONEY_QUANTUM, require_money


def money(value: Decimal) -> Decimal:
    try:
        return require_money(value)
    except ValueError:
        raise AccountingError(
            "ASSET_AMOUNT_INVALID", "금액과 소수점 자릿수를 확인해 주세요."
        ) from None


def validate_asset(value: FixedAsset) -> None:
    money(value.acquisition_cost)
    money(value.residual_value)
    if (
        value.acquisition_cost <= 0
        or not 0 <= value.residual_value <= value.acquisition_cost
        or not 1 <= value.useful_life_months <= 1200
        or value.in_service_date < value.acquisition_date
        or value.depreciation_method != "STRAIGHT_LINE"
        or value.status != "IN_SERVICE"
        or len({value.asset_account_id, value.accumulated_account_id, value.expense_account_id})
        != 3
    ):
        raise AccountingError(
            "ASSET_INPUT_INVALID", "취득원가·잔존가치·내용연수·계정을 확인해 주세요."
        )


def cumulative_depreciation(asset: FixedAsset, policy: AssetPolicy, through: date) -> Decimal:
    """Monthly schedule, with an optional first-month day fraction and residual cap.

    DAILY allocates the initial month by actual days; the outstanding fraction is
    caught up in the final month. NEXT_MONTH starts on the next calendar month.
    """
    validate_asset(asset)
    if policy.proration not in ("MONTHLY", "DAILY") or policy.acquisition_month not in (
        "FULL",
        "NEXT_MONTH",
    ):
        raise AccountingError("ASSET_POLICY_INVALID", "지원되는 월할·일할 정책을 선택해 주세요.")
    if through.day != calendar.monthrange(through.year, through.month)[1]:
        raise AccountingError("ASSET_PERIOD_INVALID", "월말 기준으로 감가상각을 계산해 주세요.")
    start = asset.in_service_date
    if policy.acquisition_month == "NEXT_MONTH":
        start = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    if through < start:
        return Decimal("0.0000")
    months = (through.year - start.year) * 12 + through.month - start.month + 1
    basis = asset.acquisition_cost - asset.residual_value
    if months >= asset.useful_life_months + (policy.proration == "DAILY" and start.day > 1):
        return basis
    elapsed = Decimal(months)
    if policy.proration == "DAILY":
        elapsed -= Decimal(start.day - 1) / Decimal(calendar.monthrange(start.year, start.month)[1])
    return min(
        basis,
        (basis * elapsed / asset.useful_life_months).quantize(
            MONEY_QUANTUM, rounding=ROUND_HALF_UP
        ),
    )
