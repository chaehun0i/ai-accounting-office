from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class Counterparty:
    id: UUID = field(default_factory=uuid4)
    company_id: UUID
    counterparty_code: str | None = None
    display_name: str
    legal_name: str
    normalized_legal_name: str
    business_number: str | None = None
    corporation_number: str | None = None
    counterparty_type: str = "BUSINESS"
    status: str = "ACTIVE"
    default_currency_code: str = "KRW"
    payment_term_id: UUID | None = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
