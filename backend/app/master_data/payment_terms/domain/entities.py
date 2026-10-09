from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class PaymentTerm:
    id: UUID = field(default_factory=uuid4)
    company_id: UUID
    term_code: str
    name: str
    due_rule_type: str
    due_days: int = 0
    is_active: bool = True
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
