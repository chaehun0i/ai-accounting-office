from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class Period:
    id: UUID = field(default_factory=uuid4)
    company_id: UUID
    fiscal_year: int
    period_no: int
    start_date: date
    end_date: date
    status: str = "OPEN"
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
