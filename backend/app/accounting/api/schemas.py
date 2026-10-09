from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.accounting.domain.rules import AccountType, BalanceSide
from app.master_data.domain.rules import CounterpartyRole, CounterpartyType, DueRule, MasterStatus


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InitializeAccountingMaster(Command):
    fiscal_year: int = Field(ge=1900, le=9998)
    template_id: UUID
    functional_currency_code: Literal[
        "KRW", "USD", "EUR", "JPY", "GBP", "CAD", "AUD", "CHF", "CNY", "SGD", "HKD"
    ] = "KRW"
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)


class SettingsUpdate(Command):
    expected_version: int = Field(ge=1)
    journal_number_prefix: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{0,9}$")
    allow_manual_journal: bool | None = None


class SettingsRead(BaseModel):
    id: UUID
    company_id: UUID
    functional_currency_code: str
    fiscal_year_start_month: int
    journal_number_prefix: str
    numbering_reset_policy: str
    allow_manual_journal: bool
    version: int


class AccountRead(BaseModel):
    id: UUID
    company_id: UUID
    template_account_id: UUID | None
    account_code: str
    account_name: str
    account_type: AccountType
    normal_balance: BalanceSide
    parent_account_id: UUID | None
    posting_allowed: bool
    is_contra: bool
    status: Literal["ACTIVE", "INACTIVE"]
    version: int


class TemplateRead(BaseModel):
    id: UUID
    template_code: str
    name: str
    version: int
    status: Literal["ACTIVE", "RETIRED"]
    valid_from: date


class PeriodRead(BaseModel):
    id: UUID
    company_id: UUID
    fiscal_year: int
    period_no: int
    start_date: date
    end_date: date
    status: Literal["OPEN", "CLOSED"]
    version: int


class PaymentTermCreate(Command):
    term_code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=1, max_length=160)
    due_rule_type: DueRule
    due_days: int = Field(default=0, ge=0, le=3650)


class PaymentTermRead(BaseModel):
    id: UUID
    company_id: UUID
    term_code: str
    name: str
    due_rule_type: DueRule
    due_days: int
    is_active: bool
    version: int


class RoleCreate(Command):
    role_code: CounterpartyRole
    effective_from: date
    effective_to: date | None = None


class RoleRead(RoleCreate):
    id: UUID
    counterparty_id: UUID


class ContactCreate(Command):
    contact_type: Literal["GENERAL", "BILLING", "SALES"]
    contact_name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    is_primary: bool = False


class ContactRead(ContactCreate):
    id: UUID
    counterparty_id: UUID


class AddressCreate(Command):
    address_type: Literal["REGISTERED", "BILLING", "SHIPPING"]
    postal_code: str | None = Field(default=None, max_length=20)
    address_line1: str = Field(min_length=1, max_length=300)
    address_line2: str | None = Field(default=None, max_length=300)
    is_primary: bool = False


class AddressRead(AddressCreate):
    id: UUID
    counterparty_id: UUID


class BankReferenceCreate(Command):
    bank_code: str = Field(min_length=1, max_length=20)
    account_alias: str = Field(min_length=1, max_length=100)
    external_token: str = Field(
        pattern=r"^vault:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", repr=False
    )


class BankReferenceRead(BaseModel):
    id: UUID
    counterparty_id: UUID
    bank_code: str
    account_alias: str
    status: Literal["ACTIVE", "INACTIVE"]


class CounterpartyCreate(Command):
    display_name: str = Field(min_length=1, max_length=200)
    legal_name: str = Field(min_length=1, max_length=200)
    business_number: str | None = Field(default=None, max_length=30)
    corporation_number: str | None = Field(default=None, max_length=30)
    counterparty_type: CounterpartyType = CounterpartyType.BUSINESS
    default_currency_code: Literal[
        "KRW", "USD", "EUR", "JPY", "GBP", "CAD", "AUD", "CHF", "CNY", "SGD", "HKD"
    ] = "KRW"
    payment_term_id: UUID | None = None
    roles: list[RoleCreate] = Field(default_factory=list, max_length=20)
    contacts: list[ContactCreate] = Field(default_factory=list, max_length=20)
    addresses: list[AddressCreate] = Field(default_factory=list, max_length=20)
    bank_refs: list[BankReferenceCreate] = Field(default_factory=list, max_length=20)


class CounterpartyUpdate(Command):
    expected_version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, min_length=1, max_length=200)
    payment_term_id: UUID | None = None
    clear_payment_term: bool = False


class CounterpartyStatusCommand(Command):
    expected_version: int = Field(ge=1)
    status: MasterStatus


class CounterpartyRead(BaseModel):
    id: UUID
    company_id: UUID
    display_name: str
    legal_name: str
    business_number: str | None
    corporation_number: str | None
    counterparty_type: CounterpartyType
    status: MasterStatus
    default_currency_code: str
    payment_term_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


class CounterpartyDetail(CounterpartyRead):
    roles: list[RoleRead]
    contacts: list[ContactRead]
    addresses: list[AddressRead]
    bank_refs: list[BankReferenceRead]


class CounterpartyFilter(Command):
    name: str | None = Field(default=None, max_length=200)
    status: MasterStatus | None = None
    role: CounterpartyRole | None = None
