"""업무 요청과 조회 응답을 분리한 재무 보조부 계약입니다."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Recognize(Command):
    journal_id: UUID
    due_date: date


class AllocationInput(Command):
    target_id: UUID
    allocated_amount: Decimal = Field(gt=0, max_digits=19, decimal_places=4)
    expected_version: int = Field(ge=1)

    @field_validator("allocated_amount", mode="before")
    @classmethod
    def no_float(cls, value: object) -> object:
        if isinstance(value, (float, bool)):
            raise ValueError("금액은 정확한 십진수 문자열로 입력해 주세요.")
        return value


class SettlementCreate(Command):
    journal_id: UUID
    settlement_date: date
    total_amount: Decimal = Field(gt=0, max_digits=19, decimal_places=4)
    method: Literal["BANK_TRANSFER", "CASH", "OTHER"] = "BANK_TRANSFER"
    reference_no: str = Field(default="", max_length=100)

    @field_validator("total_amount", mode="before")
    @classmethod
    def no_float(cls, value: object) -> object:
        return AllocationInput.no_float(value)


class Confirm(Command):
    expected_version: int = Field(ge=1)


class Allocate(Confirm):
    allocations: list[AllocationInput] = Field(max_length=200)


class ObligationRead(BaseModel):
    id: UUID
    company_id: UUID
    counterparty_id: UUID
    counterparty_name: str
    origin_journal_id: UUID
    origin_line_no: int
    account_id: UUID
    original_amount: Decimal
    outstanding_amount: Decimal
    currency_code: str
    due_date: date
    status: Literal["OPEN", "PARTIAL", "SETTLED", "WRITEOFF", "CANCELLED"]
    version: int
    origin_date: date
    source_transaction_id: UUID | None
    import_id: UUID | None
    evidence_ids: list[UUID]


class SettlementRead(BaseModel):
    id: UUID
    company_id: UUID
    journal_entry_id: UUID
    settlement_date: date
    total_amount: Decimal
    currency_code: str
    method: str
    reference_no: str
    status: Literal["DRAFT", "CONFIRMED", "UNAPPLIED"]
    version: int
    unapplied_amount: Decimal
    allocations: list[AllocationInput]


class AgingRead(BaseModel):
    as_of: date
    total_outstanding: Decimal
    overdue: Decimal
    due_7d: Decimal
    due_30d: Decimal
    buckets: dict[str, Decimal]
    counterparties: dict[UUID, Decimal]


class ReconciliationLineRead(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    subledger_amount: Decimal
    gl_amount: Decimal
    difference: Decimal
    status: Literal["MATCHED", "MISMATCH"]
    journal_ids: list[UUID]
    evidence_ids: list[UUID]


class ReconciliationRead(BaseModel):
    as_of: date
    status: Literal["MATCHED", "MISMATCH"]
    subledger_amount: Decimal
    gl_amount: Decimal
    difference: Decimal
    rows: list[ReconciliationLineRead]
