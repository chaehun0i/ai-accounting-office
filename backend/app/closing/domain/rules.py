"""기간마감의 상태 전이와 증빙 다이제스트를 결정론적으로 판정합니다."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.contracts.access_errors import StateConflict
from app.core.digests import digest

ADJUSTMENT_TYPES = frozenset(
    {
        "ACCRUED_EXPENSE",
        "ACCRUED_REVENUE",
        "PREPAID_EXPENSE_RELEASE",
        "UNEARNED_REVENUE_RELEASE",
        "MANUAL_CUTOFF_ADJUSTMENT",
    }
)
CHECK_CODES = (
    "TRANSACTIONS_PENDING",
    "JOURNALS_PENDING",
    "BANK_CARD_UNRECONCILED",
    "AR_GL_MISMATCH",
    "AP_GL_MISMATCH",
    "TRIAL_BALANCE_UNBALANCED",
    "ADJUSTMENT_INCOMPLETE",
    "CUTOFF_REVIEW",
)


@dataclass(frozen=True)
class ClosingCheck:
    code: str
    severity: str
    result_code: str
    amount_impact: Decimal = Decimal("0")
    source_type: str | None = None
    source_id: UUID | None = None


def transition_period(status: str, command: str) -> str:
    transitions = {
        ("OPEN", "start"): "CLOSING",
        ("CLOSING", "close"): "CLOSED",
        ("CLOSED", "reopen"): "OPEN",
    }
    try:
        return transitions[status, command]
    except KeyError:
        raise StateConflict() from None


def require_ready(checks: tuple[ClosingCheck, ...]) -> None:
    if any(check.severity == "BLOCKER" for check in checks):
        raise StateConflict()


def stable_digest(value: object) -> str:
    """JSON 직렬화는 해시 계산에만 쓰며 업무 DB에 payload를 저장하지 않습니다."""
    import json

    return digest(json.loads(json.dumps(value, default=str, sort_keys=True)))
