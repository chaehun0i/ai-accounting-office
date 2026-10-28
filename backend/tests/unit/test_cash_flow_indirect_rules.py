"""Golden operating bridge: exact balances, explicit relations, no residual plug."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.reporting.cash_flow.indirect import AdjustmentRule, adjustments
from tests.unit.test_cash_flow_direct_events import fact

START, END = date(2026, 1, 1), date(2026, 1, 31)


def rule(account, code, related=None):
    return AdjustmentRule(
        uuid4(),
        account,
        code,
        "ACCOUNT_LEDGER",
        related,
        START,
        None,
        1,
        "TAX_INTEREST_OPERATING",
        1,
    )


def test_non_cash_ar_ap_bridge_preserves_opening_and_line_provenance():
    cash, sales, expense, ar, ap, depreciation, accumulated = [uuid4() for _ in range(7)]
    types = {
        cash: "ASSET",
        sales: "REVENUE",
        expense: "EXPENSE",
        ar: "ASSET",
        ap: "LIABILITY",
        depreciation: "EXPENSE",
        accumulated: "ASSET",
    }
    rules = (
        rule(sales, "OPERATING_RESULT"),
        rule(expense, "OPERATING_RESULT"),
        rule(ar, "WORKING_CAPITAL"),
        rule(ap, "WORKING_CAPITAL"),
        rule(depreciation, "NONCASH_PAIR", accumulated),
        rule(accumulated, "EXCLUDED_BALANCE"),
    )
    facts = [replace(fact(uuid4(), ar, debit="40"), entry_date=date(2025, 12, 31))]
    for left, right, amount in [
        (ar, sales, "100"),
        (cash, ar, "70"),
        (expense, ap, "30"),
        (ap, cash, "20"),
        (depreciation, accumulated, "10"),
    ]:
        journal = uuid4()
        facts += [fact(journal, left, debit=amount), fact(journal, right, credit=amount)]
    result, issues = adjustments(facts, rules, types, {cash}, START, END)
    assert issues == ()
    by_account = {row.account_id: row for row in result}
    assert (by_account[ar].opening_balance, by_account[ar].closing_balance) == (
        Decimal("40"),
        Decimal("70"),
    )
    assert by_account[ar].amount == Decimal("-30")
    assert by_account[ap].amount == Decimal("10")
    assert by_account[depreciation].amount == Decimal("10")
    assert Decimal("60") + sum(row.amount for row in result) == Decimal("50")
    assert {source.journal_line_id for row in result for source in row.sources} == {
        f.line_id for f in facts if f.account_id != cash
    }
    assert adjustments(
        list(reversed(facts)), tuple(reversed(rules)), types, {cash}, START, END
    ) == (result, issues)


@pytest.mark.parametrize(
    "change,code",
    [
        ({"source_mapping_type": "INVENTORY_SUBLEDGER"}, "INDIRECT_SOURCE_UNSUPPORTED"),
        ({"source_mapping_type": "ASSET_REGISTER"}, "INDIRECT_SOURCE_UNSUPPORTED"),
        ({"policy_version": 2}, "INDIRECT_POLICY_UNSUPPORTED"),
        ({"effective_from": date(2026, 1, 2)}, "INDIRECT_RULE_NOT_FULL_PERIOD"),
        ({"effective_to": date(2026, 1, 30)}, "INDIRECT_RULE_NOT_FULL_PERIOD"),
    ],
)
def test_unavailable_sources_policy_and_partial_period_block(change, code):
    account = uuid4()
    _, issues = adjustments(
        [fact(uuid4(), account, debit="5")],
        (replace(rule(account, "WORKING_CAPITAL"), **change),),
        {account: "ASSET"},
        set(),
        START,
        END,
    )
    assert code in {issue.code for issue in issues}


def test_non_cash_addback_cannot_reverse_cash_expense_or_unknown_relation():
    expense, cash, accumulated = uuid4(), uuid4(), uuid4()
    journal = uuid4()
    facts = [fact(journal, expense, debit="10"), fact(journal, cash, credit="10")]
    _, issues = adjustments(
        facts,
        (rule(expense, "NONCASH_PAIR", accumulated),),
        {expense: "EXPENSE", accumulated: "ASSET"},
        {cash},
        START,
        END,
    )
    assert "INDIRECT_NONCASH_RELATION_UNSUPPORTED" in {i.code for i in issues}


def test_non_cash_capex_payable_is_not_operating_working_capital():
    asset, payable = uuid4(), uuid4()
    journal = uuid4()
    facts = [fact(journal, asset, debit="40"), fact(journal, payable, credit="40")]
    _, issues = adjustments(
        facts,
        (rule(asset, "EXCLUDED_BALANCE"), rule(payable, "WORKING_CAPITAL")),
        {asset: "ASSET", payable: "LIABILITY"},
        set(),
        START,
        END,
    )
    assert "INDIRECT_WORKING_CAPITAL_SOURCE_UNSUPPORTED" in {i.code for i in issues}


def test_unknown_movement_is_blocked_even_when_net_zero():
    account, journal = uuid4(), uuid4()
    _, issues = adjustments(
        [fact(journal, account, debit="1"), fact(journal, account, credit="1")],
        (),
        {account: "ASSET"},
        set(),
        START,
        END,
    )
    assert [i.code for i in issues] == ["INDIRECT_RULE_MISSING"]
