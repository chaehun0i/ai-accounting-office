from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.accounting.journals.domain.errors import AccountingError
from app.core.values import require_money


@dataclass(frozen=True, kw_only=True)
class JournalLine:
    id: UUID
    line_no: int
    account_id: UUID
    debit_amount: Decimal
    credit_amount: Decimal
    counterparty_id: UUID | None = None
    memo: str = ""


@dataclass(frozen=True, kw_only=True)
class Journal:
    id: UUID
    company_id: UUID
    accounting_period_id: UUID
    entry_date: date
    description: str
    source_type: str
    proposal_origin: str
    status: str
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    lines: tuple[JournalLine, ...]
    evidence_ids: tuple[UUID, ...] = ()
    source_transaction_id: UUID | None = None
    journal_no: str | None = None
    reversal_of_id: UUID | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    approval_id: UUID | None = None
    posted_by: UUID | None = None
    posted_at: datetime | None = None


def totals(lines: tuple[JournalLine, ...]) -> tuple[Decimal, Decimal]:
    return (
        sum((line.debit_amount for line in lines), Decimal("0")),
        sum((line.credit_amount for line in lines), Decimal("0")),
    )


def validate_lines(lines: tuple[JournalLine, ...], *, balanced: bool = True) -> None:
    if len(lines) < 2 or len(lines) > 200:
        raise AccountingError(
            "JOURNAL_LINE_INVALID", "전표에는 2개 이상 200개 이하의 분개가 필요합니다."
        )
    if len({line.line_no for line in lines}) != len(lines):
        raise AccountingError("JOURNAL_LINE_INVALID", "분개 순번이 중복되었습니다.")
    for line in lines:
        require_money(line.debit_amount)
        require_money(line.credit_amount)
        if not (
            (line.debit_amount > 0 and line.credit_amount == 0)
            or (line.credit_amount > 0 and line.debit_amount == 0)
        ):
            raise AccountingError(
                "JOURNAL_LINE_INVALID", "각 분개는 차변 또는 대변 한쪽에만 양수를 입력해 주세요."
            )
    debit, credit = totals(lines)
    require_money(debit)
    require_money(credit)
    if balanced and debit != credit:
        raise AccountingError("JOURNAL_NOT_BALANCED", "차변과 대변 합계가 일치하지 않습니다.")


TRANSITIONS = {
    "submit": ("DRAFT", "PROPOSED"),
    "request_review": ("PROPOSED", "REVIEW_REQUIRED"),
    "approve": ("REVIEW_REQUIRED", "APPROVED"),
    "reject": ("REVIEW_REQUIRED", "REJECTED"),
    "post": ("APPROVED", "POSTED"),
}


def transition(status: str, command: str) -> str:
    before, after = TRANSITIONS[command]
    if status != before:
        raise AccountingError(
            "STATE_TRANSITION_NOT_ALLOWED", "현재 전표 상태에서는 이 작업을 할 수 없습니다.", 409
        )
    return after
