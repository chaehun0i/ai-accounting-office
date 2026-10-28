"""Both cash equations must reconcile exactly before any snapshot is inserted."""

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from app.contracts.access_errors import StateConflict
from app.reporting.cash_flow.entities import CashPreflight, CashPreflightIssue
from app.reporting.cash_flow.indirect import IndirectBridge
from app.reporting.cash_flow.snapshot import require_reconciled


def ready():
    period = uuid4()
    preflight = CashPreflight(
        period,
        1,
        "a" * 64,
        "b" * 64,
        Decimal("10"),
        Decimal("110"),
        Decimal("100"),
        Decimal("100"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        1,
        (),
        True,
    )
    bridge = IndirectBridge(
        period,
        uuid4(),
        1,
        "a" * 64,
        "c" * 64,
        "TAX_INTEREST_OPERATING",
        1,
        Decimal("100"),
        (),
        Decimal("100"),
        Decimal("100"),
        Decimal("0"),
        (),
        "READY",
    )
    return preflight, bridge


def test_exact_reconciliation_is_ready():
    require_reconciled(*ready())


@pytest.mark.parametrize(
    "change",
    [
        "cash",
        "operating",
        "profit",
        "difference",
        "movement",
        "missing_set",
        "preflight",
        "bridge",
        "source",
        "version",
        "period",
        "nan",
    ],
)
def test_no_rounding_or_status_shortcuts(change):
    preflight, bridge = ready()
    tiny = Decimal("0.0001")
    if change == "cash":
        preflight = replace(preflight, closing_cash=Decimal("110") + tiny)
    elif change == "operating":
        bridge = replace(bridge, net_operating=Decimal("100") + tiny)
    elif change == "profit":
        bridge = replace(bridge, net_profit=Decimal("100") + tiny)
    elif change == "difference":
        bridge = replace(bridge, reconciliation_difference=tiny)
    elif change == "movement":
        preflight = replace(preflight, net_cash_movement=Decimal("99"))
    elif change == "missing_set":
        bridge = replace(bridge, statement_set_id=None)
    elif change == "preflight":
        preflight = replace(preflight, issues=(CashPreflightIssue("BLOCK"),))
    elif change == "bridge":
        bridge = replace(bridge, status="BLOCKED")
    elif change == "source":
        bridge = replace(bridge, source_digest="d" * 64)
    elif change == "version":
        bridge = replace(bridge, close_version=2)
    elif change == "period":
        bridge = replace(bridge, period_id=uuid4())
    elif change == "nan":
        preflight = replace(preflight, closing_cash=Decimal("NaN"))
    with pytest.raises(StateConflict):
        require_reconciled(preflight, bridge)
