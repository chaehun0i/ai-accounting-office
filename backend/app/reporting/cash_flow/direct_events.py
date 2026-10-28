"""Deterministic cash-leg pairing; ambiguous journals require evidence-backed allocation."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.accounting.ledger.domain.entities import LedgerFact
from app.reporting.cash_flow.entities import CashAllocation, CashClassification, CashEvent

ZERO = Decimal("0")


def _signed(fact: LedgerFact) -> Decimal:
    return fact.debit_amount - fact.credit_amount


def _active(classification: CashClassification | None, on: date) -> bool:
    return (
        classification is not None
        and classification.effective_from <= on
        and (classification.effective_to is None or classification.effective_to >= on)
    )


def direct_events(
    facts: list[LedgerFact],
    cash_accounts: set[UUID],
    classes: dict[UUID, CashClassification],
    allocations: tuple[CashAllocation, ...],
) -> tuple[tuple[CashEvent, ...], str | None]:
    """Return all events for one journal or a blocking code; never return a partial allocation."""
    cash = [fact for fact in facts if fact.account_id in cash_accounts]
    other = [fact for fact in facts if fact.account_id not in cash_accounts]
    if not cash:
        return (), None
    if not other and sum((_signed(fact) for fact in cash), ZERO) == ZERO:
        return (), None  # cash-to-cash transfer
    if len(cash) == 1 and len(other) == 1 and not allocations:
        cash_fact, other_fact = cash[0], other[0]
        if _signed(cash_fact) != -_signed(other_fact):
            return (), "CASH_FLOW_COMPLEX_JOURNAL"
        classification = classes.get(other_fact.account_id)
        if not _active(classification, other_fact.entry_date):
            return (), "CASH_FLOW_UNCLASSIFIED"
        assert classification is not None
        movement = _signed(cash_fact)
        return (
            CashEvent(
                cash_fact.journal_id,
                cash_fact.line_id,
                cash_fact.account_id,
                other_fact.line_id,
                other_fact.account_id,
                classification.activity_type,
                classification.line_code,
                max(movement, ZERO),
                max(-movement, ZERO),
                classification.id,
                None,
            ),
        ), None
    if not allocations:
        return (), "CASH_FLOW_COMPLEX_JOURNAL"

    cash_by_id = {fact.line_id: fact for fact in cash}
    other_by_id = {fact.line_id: fact for fact in other}
    cash_allocated: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    other_allocated: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    events: list[CashEvent] = []
    for allocation in allocations:
        allocated_cash_fact = cash_by_id.get(allocation.cash_line_id)
        allocated_other_fact = other_by_id.get(allocation.counterpart_line_id)
        if (
            allocated_cash_fact is None
            or allocated_other_fact is None
            or allocation.journal_id != allocated_cash_fact.journal_id
            or allocation.amount <= ZERO
            or _signed(allocated_cash_fact) * _signed(allocated_other_fact) >= ZERO
        ):
            return (), "CASH_FLOW_ALLOCATION_INVALID"
        classification = classes.get(allocated_other_fact.account_id)
        if not _active(classification, allocated_other_fact.entry_date):
            return (), "CASH_FLOW_UNCLASSIFIED"
        assert classification is not None
        cash_allocated[allocated_cash_fact.line_id] += allocation.amount
        other_allocated[allocated_other_fact.line_id] += allocation.amount
        inflow = allocation.amount if _signed(allocated_cash_fact) > ZERO else ZERO
        outflow = allocation.amount if _signed(allocated_cash_fact) < ZERO else ZERO
        events.append(
            CashEvent(
                allocated_cash_fact.journal_id,
                allocated_cash_fact.line_id,
                allocated_cash_fact.account_id,
                allocated_other_fact.line_id,
                allocated_other_fact.account_id,
                classification.activity_type,
                classification.line_code,
                inflow,
                outflow,
                classification.id,
                allocation.evidence_id,
            )
        )
    if any(cash_allocated[f.line_id] != abs(_signed(f)) for f in cash) or any(
        other_allocated[f.line_id] > abs(_signed(f)) for f in other
    ):
        return (), "CASH_FLOW_ALLOCATION_INCOMPLETE"
    events.sort(key=lambda item: (str(item.cash_line_id), str(item.counterpart_line_id)))
    return tuple(events), None
