from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.contracts.access_errors import InvalidInput, StateConflict
from app.reporting.cash_flow.entities import CashFlowPolicy
from app.reporting.cash_flow.service import CashFlowService, period_policy


class PolicyStore:
    def __init__(self):
        self.rows = []

    def lock_configuration(self, company):
        pass

    def policies(self, company):
        return tuple(self.rows)

    def add_policy(self, company, effective_from, version, paid, received, tax, actor, now):
        policy = CashFlowPolicy(uuid4(), effective_from, version, paid, received, tax)
        self.rows.append(policy)
        return policy


class UnitOfWork:
    def __init__(self):
        self.cash_flow = PolicyStore()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def now(self):
        return datetime.now()


def test_policy_history_is_append_only_and_chronological(monkeypatch):
    monkeypatch.setattr("app.reporting.cash_flow.service.require_company", lambda *args: None)
    uow = UnitOfWork()
    service = CashFlowService(lambda: uow)
    actor, company = SimpleNamespace(user_id=uuid4()), uuid4()
    args = (actor, company, date(2026, 1, 1), "OPERATING", "INVESTING", "OPERATING")
    first = service.create_policy(*args)
    assert first.version == 1
    assert service.create_policy(*args) == first
    with pytest.raises(StateConflict):
        service.create_policy(actor, company, date(2026, 1, 1), "FINANCING", *args[4:])
    second = service.create_policy(actor, company, date(2027, 1, 1), *args[3:])
    assert second.version == 2
    assert service.policies(actor, company) == (first, second)
    with pytest.raises(InvalidInput):
        service.create_policy(actor, company, date(2028, 1, 1), "INVESTING", *args[4:])


def test_policy_selection_rejects_mid_period_change_and_uses_next_version():
    first = CashFlowPolicy(uuid4(), date(2025, 1, 1), 1, "OPERATING", "OPERATING", "OPERATING")
    second = CashFlowPolicy(uuid4(), date(2026, 2, 1), 2, "FINANCING", "INVESTING", "OPERATING")
    assert period_policy((first, second), date(2026, 1, 1), date(2026, 1, 31)) == (first, False)
    assert period_policy((first, second), date(2026, 1, 15), date(2026, 2, 14)) == (first, True)
    assert period_policy((first, second), date(2026, 2, 1), date(2026, 2, 28)) == (second, False)
