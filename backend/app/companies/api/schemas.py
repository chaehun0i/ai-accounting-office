from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.companies.domain.entities import CompanyAccess


class CompanyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    company_name: str = Field(min_length=1, max_length=200)
    business_number: str = Field(pattern=r"^[0-9]{10}$")
    corporation_number: str | None = Field(default=None, pattern=r"^[0-9]{13}$")
    taxpayer_type: Literal["CORPORATION", "INDIVIDUAL"]
    opening_date: date
    address: str = Field(min_length=1, max_length=500)


class CompanyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, min_length=1, max_length=500)


class CompanyRead(BaseModel):
    id: UUID
    tenant_id: UUID
    company_name: str
    business_number: str
    corporation_number: str | None
    taxpayer_type: str
    opening_date: date
    address: str
    status: str
    version: int
    role_code: str
    permissions: tuple[str, ...]

    @classmethod
    def from_access(cls, access: CompanyAccess) -> "CompanyRead":
        company = access.company
        return cls(
            id=company.id,
            tenant_id=company.tenant_id,
            company_name=company.company_name,
            business_number=company.business_number,
            corporation_number=company.corporation_number,
            taxpayer_type=company.taxpayer_type,
            opening_date=company.opening_date,
            address=company.address,
            status=company.status,
            version=company.version,
            role_code=access.role_code,
            permissions=access.permissions,
        )
