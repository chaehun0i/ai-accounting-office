from decimal import Decimal
from uuid import uuid4

import pytest

from app.accounting.ledger.domain.entities import TrialRow
from app.reporting.financial_statements.domain.rules import (
    BalanceSheetUnbalanced,
    ReportMappingDuplicated,
    ReportMappingIncomplete,
    calculate,
    default_line,
)


def row(account, code, debit="0", credit="0", opening_debit="0", opening_credit="0"):
    debit, credit = Decimal(debit), Decimal(credit)
    opening_debit, opening_credit = Decimal(opening_debit), Decimal(opening_credit)
    end = opening_debit - opening_credit + debit - credit
    return TrialRow(
        account_id=account,
        account_code=code,
        account_name=code,
        opening_debit=opening_debit,
        opening_credit=opening_credit,
        period_debit=debit,
        period_credit=credit,
        ending_debit=max(end, Decimal("0")),
        ending_credit=max(-end, Decimal("0")),
        normal_balance="DEBIT",
        ending_balance=end,
    )


def test_default_template_mapping_is_explicit_by_code_not_label():
    assert default_line("EXPENSE", "5300") == "COGS"
    assert default_line("EXPENSE", "5600") == "TAX_EXPENSE"
    assert default_line("REVENUE", "4050") == "NON_OPERATING_INCOME"
    assert default_line("ASSET", "1690") == "ASSET_ACCOUNTS"


def test_decimal_income_bridge_and_untransferred_profit_balance_sheet():
    cash, revenue, expense = uuid4(), uuid4(), uuid4()
    rows = [
        row(cash, "1010", "100.1234", opening_debit="50"),
        row(revenue, "4010", credit="100.1234"),
        row(expense, "5010", "20"),
    ]
    # 비용 지급 20을 현금에서 제외해 균형을 맞춥니다.
    rows[0] = row(cash, "1010", "100.1234", "20", opening_debit="50")
    capital = uuid4()
    rows.append(row(capital, "3010", opening_credit="50"))
    mappings = [
        (cash, "ASSET_ACCOUNTS"),
        (revenue, "REVENUE"),
        (expense, "OPERATING_EXPENSE"),
        (capital, "EQUITY_ACCOUNTS"),
    ]
    result = calculate(
        rows, mappings, {cash: "ASSET", revenue: "REVENUE", expense: "EXPENSE", capital: "EQUITY"}
    )
    assert result["NET_PROFIT"] == Decimal("80.1234")
    assert result["UNTRANSFERRED_PROFIT"] == Decimal("80.1234")
    assert result["ASSETS"] == result["LIABILITIES_EQUITY"] == Decimal("130.1234")


def test_missing_duplicate_and_unbalanced_mapping_block():
    cash, equity = uuid4(), uuid4()
    rows = [row(cash, "1010", "1"), row(equity, "3010", credit="1")]
    types = {cash: "ASSET", equity: "EQUITY"}
    with pytest.raises(ReportMappingIncomplete):
        calculate(rows, [(cash, "ASSET_ACCOUNTS")], types)
    with pytest.raises(ReportMappingDuplicated):
        calculate(
            rows,
            [(cash, "ASSET_ACCOUNTS"), (cash, "ASSET_ACCOUNTS"), (equity, "EQUITY_ACCOUNTS")],
            types,
        )
    with pytest.raises(BalanceSheetUnbalanced):
        calculate(rows[:1], [(cash, "ASSET_ACCOUNTS")], types)
