from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=19, decimal_places=4)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ProfileCreate(Input):
    taxpayer_type: Literal["INDIVIDUAL_BUSINESS", "CORPORATION"]
    tax_regime: Literal["VAT_GENERAL", "VAT_SIMPLIFIED", "VAT_EXEMPT"]
    effective_from: date
    effective_to: date | None = None
    source: str = Field(min_length=1, max_length=200)
    has_employees: bool = False
    pays_business_income: bool = False
    pays_other_income: bool = False
    uses_daily_workers: bool = False
    has_exports: bool = False
    has_exempt_sales: bool = False

    @model_validator(mode="after")
    def valid_profile(self) -> Self:
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("유효기간 종료일을 확인해 주세요.")
        if self.taxpayer_type == "CORPORATION" and self.tax_regime == "VAT_SIMPLIFIED":
            raise ValueError("법인 간이과세 프로필을 사용할 수 없습니다.")
        return self


class Profile(ProfileCreate):
    id: UUID
    version: int
    created_by: UUID
    created_at: datetime


class PeriodCreate(Input):
    tax_type: Literal["VAT", "WITHHOLDING"]
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def valid_period(self) -> Self:
        if self.period_end < self.period_start:
            raise ValueError("신고 준비기간 종료일을 확인해 주세요.")
        return self


class Period(PeriodCreate):
    id: UUID
    created_by: UUID
    created_at: datetime


class VatCreate(Input):
    transaction_id: UUID
    tax_category: Literal["TAXABLE", "ZERO_RATED", "EXEMPT", "OUT_OF_SCOPE"]
    supply_amount: Money
    tax_amount: Money
    deductible_status: Literal["DEDUCTIBLE", "NON_DEDUCTIBLE", "REVIEW_REQUIRED", "NOT_APPLICABLE"]
    reason_code: str = Field(min_length=1, max_length=80)
    evidence_id: UUID | None = None
    rule_reference: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_category(self) -> Self:
        if self.tax_category != "TAXABLE" and self.tax_amount != 0:
            raise ValueError("비과세·영세율·범위 외 항목의 세액은 0이어야 합니다.")
        if self.tax_category != "TAXABLE" and self.deductible_status == "DEDUCTIBLE":
            raise ValueError("공제대상 과세 매입인지 확인해 주세요.")
        return self


class WithholdingCreate(Input):
    transaction_id: UUID
    payee_id: UUID
    income_type: Literal["EMPLOYMENT_INCOME", "BUSINESS_INCOME", "OTHER_INCOME", "DAILY_WORKER"]
    gross_amount: Money
    taxable_base: Money
    withholding_tax: Money
    local_tax: Money
    evidence_id: UUID | None = None
    rule_reference: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_amounts(self) -> Self:
        if self.taxable_base > self.gross_amount:
            raise ValueError("과세표준은 총지급액을 초과할 수 없습니다.")
        if self.withholding_tax + self.local_tax > self.gross_amount:
            raise ValueError("원천세 합계는 총지급액을 초과할 수 없습니다.")
        return self


class FactRead(Input):
    id: UUID
    revision: int
    period_id: UUID
    transaction_version: int
    source_digest: str
    created_by: UUID
    created_at: datetime


class Vat(VatCreate, FactRead):
    direction: str


class Withholding(WithholdingCreate, FactRead):
    payment_date: date
    net_amount: Decimal


class Check(Input):
    code: str
    severity: Literal["PASS", "WARN", "BLOCK"]
    source_id: UUID | None = None


class Preparation(Input):
    period: Period
    profile_ids: tuple[UUID, ...]
    vat_items: tuple[Vat, ...]
    withholding_items: tuple[Withholding, ...]
    output_tax: Decimal
    deductible_input_tax: Decimal
    vat_balance: Decimal
    withholding_tax: Decimal
    local_tax: Decimal
    net_payments: Decimal
    source_digest: str
    checks: tuple[Check, ...]
    status: Literal["NOT_STARTED", "NEEDS_REVIEW"]
    ready_to_file: Literal[False] = False
