from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_date: date
    accounting_date: date
    description: str = Field(min_length=1, max_length=2000)
    amount: Decimal = Field(gt=0, max_digits=19, decimal_places=4)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=19, decimal_places=4)
    currency_code: Literal["KRW"] = "KRW"
    direction: Literal["INFLOW", "OUTFLOW"]
    source_type: Literal[
        "MANUAL", "BANK_TRANSACTION", "CARD_TRANSACTION", "SALES", "PURCHASE", "EXPENSE"
    ] = "MANUAL"
    source_system: str = Field(default="MANUAL", min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=100)
    counterparty_id: UUID | None = None
    import_id: UUID | None = None
    evidence_id: UUID | None = None
    payment_method: Literal["UNSPECIFIED", "BANK", "CARD", "CASH"] = "UNSPECIFIED"

    @field_validator("amount", "tax_amount", mode="before")
    @classmethod
    def no_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("금액은 소수 문자열로 입력해 주세요.")
        return value


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=2000)


class TransactionRead(TransactionCreate):
    id: UUID
    company_id: UUID
    source_fingerprint: str
    status: str
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
