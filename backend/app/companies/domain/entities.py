from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


@dataclass
class Company:
    id: UUID
    tenant_id: UUID
    company_name: str
    business_number: str
    taxpayer_type: str
    opening_date: date
    address: str
    corporation_number: str | None = None
    status: str = "ACTIVE"
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    timezone: str = "Asia/Seoul"


@dataclass(frozen=True)
class CompanyAccess:
    company: Company
    role_code: str
    permissions: tuple[str, ...]
