from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Generate(Input):
    period_id: UUID


class MappingCreate(Input):
    period_id: UUID
    account_id: UUID
    line_code: Literal[
        "ASSET_ACCOUNTS",
        "LIABILITY_ACCOUNTS",
        "EQUITY_ACCOUNTS",
        "REVENUE",
        "COGS",
        "OPERATING_EXPENSE",
        "NON_OPERATING_INCOME",
        "NON_OPERATING_EXPENSE",
        "TAX_EXPENSE",
    ]


class MappingRead(Input):
    account_id: UUID
    line_code: str


class StatementSetRead(Input):
    id: UUID
    company_id: UUID
    period_id: UUID
    closing_run_id: UUID
    close_version: int
    taxonomy_id: UUID
    taxonomy_version: int
    status: Literal["GENERATED"]
    trial_balance_digest: str
    mapping_digest: str
    generated_at: datetime


class StatementLineRead(Input):
    id: UUID
    line_code: str
    label: str
    parent_code: str | None
    display_order: int
    subtotal_type: Literal["LEAF", "DERIVED", "TOTAL"]
    current_amount: Decimal = Field(max_digits=19, decimal_places=4)


class StatementRead(Input):
    id: UUID
    set_id: UUID
    statement_type: Literal["BALANCE_SHEET", "INCOME_STATEMENT"]
    status: Literal["GENERATED"]
    snapshot_digest: str
    lines: tuple[StatementLineRead, ...]


class SourceRead(Input):
    account_id: UUID
    account_code: str
    account_name: str
    journal_id: UUID
    journal_line_id: UUID
    journal_no: str
    entry_date: str
    amount: Decimal = Field(max_digits=19, decimal_places=4)
