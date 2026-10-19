from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.accounting.control_accounts.api.approval_schemas import ChangeRequestRead
from app.accounting.control_accounts.domain.roles import ControlAccountRole


class MappingRead(BaseModel):
    role: ControlAccountRole
    account_id: UUID | None
    version: int


class RequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: ControlAccountRole
    target_account_id: UUID
    expected_mapping_version: int = Field(ge=0)
    expected_target_account_version: int = Field(ge=1)


class ImpactFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    subject: str
    count: int
    blocking: bool


class ImpactRead(BaseModel):
    digest: str
    blocking: bool
    facts: list[ImpactFactRead]


__all__ = ["MappingRead", "RequestCreate", "ImpactRead", "ChangeRequestRead"]
