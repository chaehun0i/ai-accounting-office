from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.accounting.transactions.api.schemas import TransactionCreate


class LineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    debit_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=19, decimal_places=4)
    credit_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=19, decimal_places=4)
    counterparty_id: UUID | None = None
    memo: str = Field(default="", max_length=2000)

    @field_validator("debit_amount", "credit_amount", mode="before")
    @classmethod
    def no_float(cls, value: object) -> object:
        return TransactionCreate.no_float(value)


class LineRead(LineCreate):
    id: UUID
    line_no: int


class JournalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accounting_period_id: UUID
    entry_date: date
    description: str = Field(min_length=1, max_length=2000)
    source_type: Literal["MANUAL", "TRANSACTION"] = "MANUAL"
    source_transaction_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=50)
    lines: list[LineCreate] = Field(min_length=2, max_length=200)


class JournalUpdate(JournalCreate):
    expected_version: int = Field(ge=1)


class JournalRead(BaseModel):
    id: UUID
    company_id: UUID
    accounting_period_id: UUID
    entry_date: date
    description: str
    source_type: str
    source_transaction_id: UUID | None
    status: str
    version: int
    created_by: UUID
    journal_no: str | None
    reversal_of_id: UUID | None
    approval_id: UUID | None
    approved_by: UUID | None
    approved_at: datetime | None
    posted_at: datetime | None
    lines: list[LineRead]
    evidence_ids: list[UUID]
    total_debit: Decimal
    total_credit: Decimal
    difference: Decimal


class JournalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(default="", max_length=2000)
    approval_id: UUID | None = None
    reversal_date: date | None = None
