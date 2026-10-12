"""금융 원천의 권한 문맥은 요청 본문으로 받지 않습니다."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def no_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("금액은 소수 문자열로 입력해 주세요.")
        return value


class AccountCreate(Input):
    institution_code: str = Field(min_length=1, max_length=30)
    alias: str = Field(min_length=1, max_length=80)
    control_account_id: UUID
    usage_type: Literal["CORPORATE", "MERCHANT"] = "CORPORATE"


class SourceImport(Input):
    account_id: UUID
    import_id: UUID
    receipt_id: UUID
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed_version: int = Field(ge=1)


class StatementImport(SourceImport):
    statement_start: date
    statement_end: date
    opening_balance: Decimal = Field(max_digits=19, decimal_places=4)
    closing_balance: Decimal = Field(max_digits=19, decimal_places=4)


class MatchLine(Input):
    source_type: Literal["BANK", "CARD"]
    source_id: UUID
    target_type: Literal["COLLECTION", "PAYMENT", "TRANSACTION"]
    target_id: UUID
    amount: Decimal = Field(gt=0, max_digits=19, decimal_places=4)
    source_version: int = Field(ge=1)
    target_version: int = Field(ge=1)


class MatchCreate(Input):
    lines: list[MatchLine] = Field(min_length=1, max_length=500)


class Confirm(Input):
    expected_version: int = Field(ge=1)


class Unmatch(Confirm):
    reason: str = Field(max_length=500)


class ResolveItem(Confirm):
    resolution_note: str = Field(min_length=1, max_length=500)


class ItemCreate(Input):
    reason_code: Literal[
        "TIMING_ITEM",
        "MISSING_TRANSACTION",
        "DUPLICATE_SOURCE",
        "WRONG_ACCOUNT",
        "MANUAL_ADJUSTMENT_CANDIDATE",
        "UNKNOWN",
    ]
    amount: Decimal = Field(max_digits=19, decimal_places=4)
    description: str = Field(min_length=1, max_length=500)
