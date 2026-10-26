"""현금 범위와 사전 점검 응답의 타입 계약."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class CashScope:
    id: UUID
    account_id: UUID
    scope_type: str
    effective_from: date
    effective_to: date | None
    version: int


@dataclass(frozen=True)
class CashClassification:
    id: UUID
    account_id: UUID
    activity_type: str
    line_code: str
    effective_from: date
    effective_to: date | None
    version: int


@dataclass(frozen=True)
class CashPreflightIssue:
    code: str
    journal_id: UUID | None = None


@dataclass(frozen=True)
class CashPreflight:
    period_id: UUID
    close_version: int
    source_digest: str
    mapping_digest: str
    opening_cash: Decimal
    closing_cash: Decimal
    net_cash_movement: Decimal
    net_operating: Decimal
    net_investing: Decimal
    net_financing: Decimal
    exchange_effect: Decimal
    classified_journal_count: int
    issues: tuple[CashPreflightIssue, ...]
    ready: bool
