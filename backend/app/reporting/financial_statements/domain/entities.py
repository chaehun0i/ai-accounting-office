from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class StatementSet:
    id: UUID
    company_id: UUID
    period_id: UUID
    closing_run_id: UUID
    close_version: int
    taxonomy_id: UUID
    taxonomy_version: int
    status: str
    trial_balance_digest: str
    mapping_digest: str
    generated_at: datetime


@dataclass(frozen=True)
class StatementLine:
    id: UUID
    line_code: str
    label: str
    parent_code: str | None
    display_order: int
    subtotal_type: str
    current_amount: Decimal


@dataclass(frozen=True)
class StatementView:
    id: UUID
    set_id: UUID
    statement_type: str
    status: str
    snapshot_digest: str
    lines: tuple[StatementLine, ...]


@dataclass(frozen=True)
class SourceLine:
    account_id: UUID
    account_code: str
    account_name: str
    journal_id: UUID
    journal_line_id: UUID
    journal_no: str
    entry_date: str
    amount: Decimal
