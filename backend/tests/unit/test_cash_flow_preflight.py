"""현금 이동 사전 점검은 OPENING과 복합분개를 임의로 분류하지 않습니다."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.accounting.ledger.domain.entities import LedgerFact
from app.reporting.cash_flow.entities import CashClassification, CashScope
from app.reporting.cash_flow.service import CashFlowService


class _CashStore:
    def __init__(self, scopes, classes):
        self._scopes = scopes
        self._classes = classes

    def scopes(self, _company):
        return self._scopes

    def classifications(self, _company):
        return self._classes

    def allocations(self, _company):
        return ()


class _UnitOfWork:
    def __init__(self, scopes, classes):
        self.cash_flow = _CashStore(scopes, classes)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def _fact(journal, account, debit="0", credit="0", source="MANUAL"):
    return LedgerFact(
        journal_id=journal,
        line_id=uuid4(),
        entry_date=date(2026, 1, 2),
        journal_no="2026-1",
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
        source_type=source,
    )


def _preflight(monkeypatch, facts, cash, activity):
    company, period_id = uuid4(), uuid4()
    scopes = (CashScope(uuid4(), cash, "CASH", date(2026, 1, 1), None, 1),)
    classes = (
        CashClassification(uuid4(), activity, "OPERATING", "RECEIPTS", date(2026, 1, 1), None, 1),
    )
    period = SimpleNamespace(
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31), close_version=1
    )
    monkeypatch.setattr("app.reporting.cash_flow.service.require_company", lambda *_args: None)
    monkeypatch.setattr(
        "app.reporting.cash_flow.service.ClosingService.closed_adjusted_source",
        lambda *_args: (period, None, "source-digest", [], facts),
    )
    service = CashFlowService(lambda: _UnitOfWork(scopes, classes))
    return service.preflight(SimpleNamespace(user_id=uuid4()), company, period_id)


def test_opening_cash_is_not_current_period_activity(monkeypatch):
    cash, revenue = uuid4(), uuid4()
    opening = uuid4()
    sale = uuid4()
    facts = [
        _fact(opening, cash, debit="50", source="OPENING"),
        _fact(opening, uuid4(), credit="50", source="OPENING"),
        _fact(sale, cash, debit="100"),
        _fact(sale, revenue, credit="100"),
    ]
    result = _preflight(monkeypatch, facts, cash, revenue)
    assert result.ready and not result.issues
    assert (result.opening_cash, result.net_operating, result.closing_cash) == (
        Decimal("50"),
        Decimal("100"),
        Decimal("150"),
    )
    assert result.classified_journal_count == 1


def test_complex_journal_remains_blocked_without_allocation(monkeypatch):
    cash, revenue = uuid4(), uuid4()
    journal = uuid4()
    facts = [
        _fact(journal, cash, debit="100"),
        _fact(journal, revenue, credit="80"),
        _fact(journal, uuid4(), credit="20"),
    ]
    result = _preflight(monkeypatch, facts, cash, revenue)
    assert not result.ready
    assert [(issue.code, issue.journal_id) for issue in result.issues] == [
        ("CASH_FLOW_COMPLEX_JOURNAL", journal)
    ]
    assert result.net_operating == Decimal("0")
