"""거래는 경제적 사건이며 전표와 별개의 원천 정본입니다."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class Transaction:
    id: UUID
    company_id: UUID
    transaction_date: date
    accounting_date: date
    description: str
    amount: Decimal
    currency_code: str
    direction: str
    source_type: str
    source_system: str
    source_id: str
    source_fingerprint: str
    status: str
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    counterparty_id: UUID | None = None
    import_id: UUID | None = None
    evidence_id: UUID | None = None
    tax_amount: Decimal = Decimal("0")
    payment_method: str = "UNSPECIFIED"
