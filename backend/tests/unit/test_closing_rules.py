from decimal import Decimal

import pytest

from app.closing.domain.rules import ClosingCheck, require_ready, stable_digest, transition_period
from app.contracts.access_errors import StateConflict


def test_period_transitions_and_blockers() -> None:
    assert transition_period("OPEN", "start") == "CLOSING"
    assert transition_period("CLOSING", "close") == "CLOSED"
    assert transition_period("CLOSED", "reopen") == "OPEN"
    with pytest.raises(StateConflict):
        transition_period("OPEN", "close")
    require_ready((ClosingCheck("BANK", "WARNING", "TIMING", Decimal("1.0000")),))
    with pytest.raises(StateConflict):
        require_ready((ClosingCheck("BANK", "BLOCKER", "DIFFERENCE"),))


def test_digest_is_deterministic_and_amount_safe() -> None:
    assert stable_digest({"amount": Decimal("1.0000"), "status": "PASS"}) == stable_digest(
        {"status": "PASS", "amount": Decimal("1.0000")}
    )
    assert stable_digest({"amount": Decimal("1.0000")}) != stable_digest(
        {"amount": Decimal("1.0001")}
    )
