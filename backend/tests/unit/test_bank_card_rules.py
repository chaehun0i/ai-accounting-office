from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.contracts.access_errors import InvalidInput
from app.finance.cards.domain.rules import direction_for, normalize_status
from app.finance.reconciliation.domain.rules import (
    AmountExceeded,
    MatchFact,
    MatchingPolicy,
    closing_balance,
    money,
    reconciliation_status,
    score_candidate,
    source_fingerprint,
)


def fact(amount: str = "100", direction: str = "IN") -> MatchFact:
    return MatchFact(
        uuid4(),
        "TRANSACTION",
        date(2026, 1, 1),
        direction,
        Decimal(amount),
        Decimal(0),
        1,
        "REF1",
        "고객",
    )


def test_scoring_is_deterministic_and_direction_safe() -> None:
    source, target = fact(), fact()
    result = score_candidate(source, target, MatchingPolicy())
    assert result == score_candidate(source, target, MatchingPolicy())
    assert result and result.score == 100 and result.classification == "AUTO_MATCHED"
    assert score_candidate(source, fact(direction="OUT"), MatchingPolicy()) is None


def test_partial_and_statement_balance() -> None:
    result = score_candidate(fact("100"), fact("60"), MatchingPolicy())
    assert result and result.suggested_amount == Decimal("60")
    assert result.classification == "REVIEW_CANDIDATE"
    assert closing_balance(Decimal("10"), [fact("100"), fact("60", "OUT")]) == Decimal("50")
    assert reconciliation_status(Decimal(100), Decimal(20)) == "PARTIAL"
    assert reconciliation_status(Decimal(100), Decimal(100)) == "MATCHED"
    assert reconciliation_status(Decimal(100), Decimal(0), review=True) == "REVIEW"
    with pytest.raises(AmountExceeded):
        reconciliation_status(Decimal(100), Decimal(101))


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), 0.1])
def test_invalid_money_fails(value: Decimal) -> None:
    with pytest.raises(InvalidInput):
        money(value)


def test_card_status_and_source_identity() -> None:
    assert normalize_status("취소") == "CANCELLED"
    assert normalize_status("환불") == "REFUNDED"
    assert direction_for("REFUNDED") == "IN"
    with pytest.raises(InvalidInput):
        normalize_status("모름")
    assert source_fingerprint(["a", "bc"]) != source_fingerprint(["ab", "c"])
