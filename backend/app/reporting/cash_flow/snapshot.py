"""Frozen relational cash flow response contracts and exact reconciliation gate."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.contracts.access_errors import StateConflict
from app.reporting.cash_flow.entities import CashEvent, CashPreflight, NoncashDisclosure
from app.reporting.cash_flow.indirect import IndirectBridge


@dataclass(frozen=True)
class CashStatement:
    id: UUID
    period_id: UUID
    statement_set_id: UUID
    balance_sheet_id: UUID
    balance_sheet_digest: str
    income_statement_id: UUID
    income_statement_digest: str
    close_version: int
    source_digest: str
    mapping_digest: str
    direct_mapping_digest: str
    snapshot_digest: str
    policy_code: str
    policy_version: int
    method: str
    status: str
    opening_cash: Decimal
    closing_cash: Decimal
    net_profit: Decimal
    net_operating: Decimal
    net_investing: Decimal
    net_financing: Decimal
    exchange_effect: Decimal
    generated_at: datetime


@dataclass(frozen=True)
class CashLine:
    id: UUID
    line_code: str
    amount: Decimal
    source_type: str
    source_id: UUID | None
    display_order: int


@dataclass(frozen=True)
class FrozenEvent(CashEvent):
    id: UUID
    classification_version: int
    allocation_id: UUID | None
    allocation_version: int | None


@dataclass(frozen=True)
class FrozenAdjustment:
    id: UUID
    rule_id: UUID
    rule_version: int
    account_id: UUID
    adjustment_code: str
    opening_balance: Decimal
    closing_balance: Decimal
    amount: Decimal


@dataclass(frozen=True)
class CashSource:
    adjustment_id: UUID
    journal_id: UUID
    journal_line_id: UUID
    entry_date: date
    signed_debit_amount: Decimal
    is_opening: bool


@dataclass(frozen=True)
class CashBalanceSource:
    scope_id: UUID
    scope_version: int
    account_id: UUID
    journal_id: UUID
    journal_line_id: UUID
    entry_date: date
    signed_debit_amount: Decimal
    is_opening: bool


@dataclass(frozen=True)
class JournalTrace:
    journal_id: UUID
    transaction_id: UUID | None
    evidence_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class CashDrilldown:
    statement_id: UUID
    lines: tuple[CashLine, ...]
    events: tuple[FrozenEvent, ...]
    adjustments: tuple[FrozenAdjustment, ...]
    adjustment_sources: tuple[CashSource, ...]
    cash_balance_sources: tuple[CashBalanceSource, ...]
    journals: tuple[JournalTrace, ...]
    noncash_disclosures: tuple[NoncashDisclosure, ...] = ()


def require_reconciled(preflight: CashPreflight, bridge: IndirectBridge) -> None:
    """Never tolerate, round, or plug a difference before freezing the result."""
    values = (
        preflight.opening_cash,
        preflight.closing_cash,
        preflight.net_cash_movement,
        preflight.net_operating,
        preflight.net_investing,
        preflight.net_financing,
        preflight.exchange_effect,
        bridge.net_profit,
        bridge.net_operating,
        bridge.direct_net_operating,
        bridge.reconciliation_difference,
        *(row.amount for row in bridge.adjustments),
    )
    if (
        not preflight.ready
        or preflight.issues
        or bridge.status != "READY"
        or bridge.issues
        or bridge.statement_set_id is None
        or any(value is None or not value.is_finite() for value in values)
        or (preflight.period_id, preflight.close_version, preflight.source_digest)
        != (bridge.period_id, bridge.close_version, bridge.source_digest)
        or bridge.reconciliation_difference != Decimal("0")
        or bridge.net_operating != preflight.net_operating
        or bridge.direct_net_operating != preflight.net_operating
        or bridge.net_profit is None
        or bridge.net_profit + sum((a.amount for a in bridge.adjustments), Decimal("0"))
        != bridge.net_operating
        or preflight.closing_cash - preflight.opening_cash != preflight.net_cash_movement
        or preflight.opening_cash
        + preflight.net_operating
        + preflight.net_investing
        + preflight.net_financing
        + preflight.exchange_effect
        != preflight.closing_cash
    ):
        raise StateConflict()
