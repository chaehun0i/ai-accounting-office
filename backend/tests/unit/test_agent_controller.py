import pytest

from app.agents.runtime.controller import verdict


@pytest.mark.parametrize(
    "error",
    [
        "JOURNAL_NOT_BALANCED",
        "ACCOUNT_NOT_FOUND",
        "UNSUPPORTED_NUMBER",
        "EVIDENCE_MISMATCH",
        "PERIOD_NOT_OPEN",
        "AUTHORIZATION_DENIED",
    ],
)
def test_hard_rule_always_blocks(error):
    assert verdict([error], True, "SALES") == "BLOCK"


def test_evidence_and_uncertainty_require_review():
    assert verdict([], False, "SALES") == "REVIEW"
    assert verdict([], True, "OTHER") == "REVIEW"
    assert verdict([], True, "SALES") == "PASS"
