"""기준일이 명시된 에이징과 원장 대사 결과 계약입니다."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.finance.receivables.domain.entities import Obligation
from app.finance.settlements.domain.rules import ZERO, aging_bucket


@dataclass(frozen=True)
class AgingSummary:
    as_of: date
    total_outstanding: Decimal
    overdue: Decimal
    due_7d: Decimal
    due_30d: Decimal
    buckets: dict[str, Decimal]
    counterparties: dict[UUID, Decimal]


def aging(values: list[Obligation], as_of: date) -> AgingSummary:
    open_values = [value for value in values if value.outstanding_amount > ZERO]
    buckets = dict.fromkeys(("CURRENT", "1-30", "31-60", "61-90", "90+"), ZERO)
    counterparties: dict[UUID, Decimal] = {}
    for value in open_values:
        buckets[aging_bucket(value.due_date, as_of)] += value.outstanding_amount
        key = value.counterparty_id
        counterparties[key] = counterparties.get(key, ZERO) + value.outstanding_amount

    def due_within(days: int) -> Decimal:
        return sum(
            (
                value.outstanding_amount
                for value in open_values
                if as_of <= value.due_date <= as_of + timedelta(days=days)
            ),
            ZERO,
        )

    return AgingSummary(
        as_of,
        sum((value.outstanding_amount for value in open_values), ZERO),
        sum((value.outstanding_amount for value in open_values if value.due_date < as_of), ZERO),
        due_within(7),
        due_within(30),
        buckets,
        counterparties,
    )


@dataclass(frozen=True)
class ReconciliationRow:
    account_id: UUID
    account_code: str
    account_name: str
    subledger_amount: Decimal
    gl_amount: Decimal
    difference: Decimal
    status: str
    journal_ids: tuple[UUID, ...]
    evidence_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class Reconciliation:
    as_of: date
    status: str
    subledger_amount: Decimal
    gl_amount: Decimal
    difference: Decimal
    rows: tuple[ReconciliationRow, ...]
