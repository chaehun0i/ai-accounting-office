from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class Account:
    id: UUID = field(default_factory=uuid4)
    company_id: UUID
    account_code: str
    account_name: str
    account_type: str
    normal_balance: str
    posting_allowed: bool
    is_contra: bool = False
    template_account_id: UUID | None = None
    parent_account_id: UUID | None = None
    status: str = "ACTIVE"
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
