"""은행·카드 원천과 업무 사실의 대사는 장부 계산과 분리합니다."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.contracts.access_errors import InvalidInput, StateConflict
from app.core.values import require_money
from app.intake.domain.digest import digest

ZERO = Decimal("0")


class AmountExceeded(InvalidInput):
    code = "RECONCILIATION_AMOUNT_EXCEEDED"
    message = "대사 금액이 원천 또는 대상의 남은 금액을 초과합니다."


class SourceStale(StateConflict):
    code = "RECONCILIATION_SOURCE_STALE"
    message = "대사 자료가 변경되었습니다. 후보를 다시 조회해 주세요."


class StatementNotBalanced(InvalidInput):
    code = "BANK_STATEMENT_NOT_BALANCED"
    message = "기초잔액과 입출금 합계가 명세의 기말잔액과 일치하지 않습니다."


class UnmatchReasonRequired(InvalidInput):
    code = "RECONCILIATION_UNMATCH_REQUIRES_REASON"
    message = "대사 해제 사유를 입력해 주세요."


@dataclass(frozen=True)
class MatchingPolicy:
    version: int = 1
    allowed_days: int = 7
    amount_tolerance: Decimal = ZERO
    auto_threshold: int = 90
    review_threshold: int = 40
    materiality: Decimal = ZERO

    def validate(self) -> None:
        if not (1 <= self.version and 0 <= self.allowed_days <= 90):
            raise InvalidInput()
        if not 0 <= self.review_threshold <= self.auto_threshold <= 100:
            raise InvalidInput()
        for value in [self.amount_tolerance, self.materiality]:
            money(value, positive=False)


@dataclass(frozen=True)
class MatchFact:
    id: UUID
    kind: str
    occurred_on: date
    direction: str
    amount: Decimal
    matched_amount: Decimal
    version: int
    reference: str = ""
    party: str = ""
    source_status: str = "CAPTURED"

    @property
    def remaining(self) -> Decimal:
        return self.amount - self.matched_amount


@dataclass(frozen=True)
class Candidate:
    source_id: UUID
    target_type: str
    target_id: UUID
    source_version: int
    target_version: int
    remaining_amount: Decimal
    suggested_amount: Decimal
    score: int
    classification: str
    reasons: tuple[str, ...]
    policy_version: int
    target_reference: str = ""
    target_date: date | None = None


def money(value: Decimal, *, positive: bool = True) -> Decimal:
    try:
        require_money(value)
    except (ValueError, TypeError) as error:
        raise InvalidInput() from error
    if value < ZERO or (positive and value == ZERO):
        raise InvalidInput()
    return value


def safe_reference(value: str, *, maximum: int = 100) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1," + str(maximum) + r"}", value):
        raise InvalidInput()
    return value


def reconciliation_status(amount: Decimal, matched: Decimal, *, review: bool = False) -> str:
    if matched < ZERO or matched > amount:
        raise AmountExceeded()
    if matched == amount:
        return "MATCHED"
    if matched > ZERO:
        return "PARTIAL"
    return "REVIEW" if review else "UNMATCHED"


def closing_balance(opening: Decimal, sources: list[MatchFact]) -> Decimal:
    require_money(opening)
    return opening + sum(
        (fact.amount if fact.direction == "IN" else -fact.amount for fact in sources), ZERO
    )


def score_candidate(
    source: MatchFact, target: MatchFact, policy: MatchingPolicy
) -> Candidate | None:
    policy.validate()
    days = abs((source.occurred_on - target.occurred_on).days)
    if source.direction != target.direction or days > policy.allowed_days:
        return None
    if source.remaining <= ZERO or target.remaining <= ZERO:
        return None
    if source.source_status in {"AUTHORIZED", "CANCELLED", "REVERSED"}:
        return None
    exact = abs(source.remaining - target.remaining) <= policy.amount_tolerance
    reasons = [
        "AMOUNT_EXACT" if exact else "PARTIAL_AMOUNT",
        "DATE_EXACT" if days == 0 else "DATE_NEAR",
    ]
    score = (60 if exact else 20) + max(0, 20 - days * 2)
    if source.reference and source.reference == target.reference:
        score += 15
        reasons.append("REFERENCE_EXACT")
    if source.party and source.party.casefold().strip() == target.party.casefold().strip():
        score += 5
        reasons.append("COUNTERPARTY_EXACT")
    classification = (
        "AUTO_MATCHED"
        if score >= policy.auto_threshold
        else "REVIEW_CANDIDATE"
        if score >= policy.review_threshold
        else "UNMATCHED"
    )
    return Candidate(
        source.id,
        target.kind,
        target.id,
        source.version,
        target.version,
        target.remaining,
        min(source.remaining, target.remaining),
        score,
        classification,
        tuple(reasons),
        policy.version,
        target.reference,
        target.occurred_on,
    )


def source_fingerprint(values: list[str]) -> str:
    return digest(["financial-source-v1", *values])
