from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApprovalCommand(BaseModel):
    expected_version: int = Field(ge=1)


class RejectionCommand(ApprovalCommand):
    reason: str = Field(min_length=1, max_length=500)


class ChangeRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    role: str
    current_account_id: UUID | None
    target_account_id: UUID
    expected_mapping_version: int
    expected_target_account_version: int
    impact_digest: str
    status: str
    requester_id: UUID
    approver_id: UUID | None
    approved_at: datetime | None
    rejected_at: datetime | None
    executed_by_id: UUID | None
    executed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class ChangeEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    request_id: UUID
    role: str
    event_type: str
    reason: str | None
    actor_id: UUID
    before_account_id: UUID | None
    after_account_id: UUID | None
    occurred_at: datetime
