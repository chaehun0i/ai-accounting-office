from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class Role:
    counterparty_id: UUID
    role_code: str
    effective_from: date
    effective_to: date | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, kw_only=True)
class Contact:
    counterparty_id: UUID
    contact_type: str
    contact_name: str
    email: str | None = None
    phone: str | None = None
    is_primary: bool = False
    id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, kw_only=True)
class Address:
    counterparty_id: UUID
    address_type: str
    address_line1: str
    postal_code: str | None = None
    address_line2: str | None = None
    is_primary: bool = False
    id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, kw_only=True)
class BankReference:
    counterparty_id: UUID
    bank_code: str
    account_alias: str
    external_token: str = field(repr=False)
    status: str = "ACTIVE"
    id: UUID = field(default_factory=uuid4)
