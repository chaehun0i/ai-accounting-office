"""Cash-leg allocation must be explicit and exact for complex journals."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.accounting.ledger.domain.entities import LedgerFact
from app.reporting.cash_flow.direct_events import direct_events
from app.reporting.cash_flow.entities import CashAllocation, CashClassification


def fact(journal, account, *, debit="0", credit="0"):
    return LedgerFact(
        journal_id=journal,
        line_id=uuid4(),
        entry_date=date(2026, 1, 2),
        journal_no="TEST-1",
        account_id=account,
        account_code="TEST",
        account_name="TEST",
        normal_balance="DEBIT",
        counterparty_id=None,
        description="test",
        debit_amount=Decimal(debit),
        credit_amount=Decimal(credit),
        source_transaction_id=None,
        import_id=None,
    )


def test_complex_journal_uses_exact_explicit_pairs():
    journal, cash_account, revenue, tax = (uuid4() for _ in range(4))
    cash = fact(journal, cash_account, debit="110")
    sale = fact(journal, revenue, credit="100")
    vat = fact(journal, tax, credit="10")
    classes = {
        revenue: CashClassification(
            uuid4(), revenue, "OPERATING", "RECEIPTS", date(2026, 1, 1), None, 1
        ),
        tax: CashClassification(
            uuid4(), tax, "OPERATING", "VAT_RECEIPTS", date(2026, 1, 1), None, 1
        ),
    }
    allocations = (
        CashAllocation(
            uuid4(), journal, cash.line_id, sale.line_id, uuid4(), Decimal("100"), 1, None
        ),
        CashAllocation(
            uuid4(), journal, cash.line_id, vat.line_id, uuid4(), Decimal("10"), 1, None
        ),
    )
    events, issue = direct_events([cash, sale, vat], {cash_account}, classes, allocations)
    assert issue is None
    assert {(e.line_code, e.cash_inflow, e.cash_outflow) for e in events} == {
        ("RECEIPTS", Decimal("100"), Decimal("0")),
        ("VAT_RECEIPTS", Decimal("10"), Decimal("0")),
    }
    assert sum((e.cash_inflow - e.cash_outflow for e in events), Decimal("0")) == Decimal("110")
    incomplete, issue = direct_events([cash, sale, vat], {cash_account}, classes, allocations[:1])
    assert incomplete == () and issue == "CASH_FLOW_ALLOCATION_INCOMPLETE"


def test_unallocated_complex_and_mixed_cash_transfer_remain_blocked():
    journal, cash_a, cash_b, revenue, payable = (uuid4() for _ in range(5))
    facts = [
        fact(journal, cash_a, debit="120"),
        fact(journal, cash_b, credit="20"),
        fact(journal, revenue, credit="80"),
        fact(journal, payable, credit="20"),
    ]
    events, issue = direct_events(facts, {cash_a, cash_b}, {}, ())
    assert events == () and issue == "CASH_FLOW_COMPLEX_JOURNAL"


def test_cash_only_transfer_is_excluded():
    journal, cash_a, cash_b = (uuid4() for _ in range(3))
    facts = [fact(journal, cash_a, debit="50"), fact(journal, cash_b, credit="50")]
    events, issue = direct_events(facts, {cash_a, cash_b}, {}, ())
    assert events == () and issue is None


def test_cash_part_of_asset_purchase_does_not_allocate_non_cash_remainder():
    journal, cash_account, asset_account, payable_account = (uuid4() for _ in range(4))
    cash = fact(journal, cash_account, credit="60")
    asset = fact(journal, asset_account, debit="100")
    payable = fact(journal, payable_account, credit="40")
    classification = CashClassification(
        uuid4(), asset_account, "INVESTING", "ASSET_PURCHASE", date(2026, 1, 1), None, 1
    )
    allocation = CashAllocation(
        uuid4(), journal, cash.line_id, asset.line_id, uuid4(), Decimal("60"), 1, None
    )
    events, issue = direct_events(
        [cash, asset, payable], {cash_account}, {asset_account: classification}, (allocation,)
    )
    assert issue is None and len(events) == 1
    assert events[0].cash_outflow == Decimal("60")
