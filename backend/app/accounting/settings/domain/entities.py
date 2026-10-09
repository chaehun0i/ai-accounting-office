from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class AccountingSettings:
    id: UUID = field(default_factory=uuid4)
    company_id: UUID
    functional_currency_code: str = "KRW"
    fiscal_year_start_month: int = 1
    journal_number_prefix: str = "J"
    numbering_reset_policy: str = "FISCAL_YEAR"
    allow_manual_journal: bool = True
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
