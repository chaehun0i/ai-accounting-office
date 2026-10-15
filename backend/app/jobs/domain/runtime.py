"""제품 실행 이력은 프레임워크 체크포인트와 별도로 유지합니다."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

RunStatus = Literal["PENDING", "RUNNING", "WAITING_FOR_INPUT", "COMPLETED", "BLOCKED", "FAILED"]


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
    job_id: UUID
    transaction_id: UUID | None
    period_id: UUID | None
    question_text: str | None
    answer_text: str | None
    answer_amount: Decimal | None
    answer_resource_id: UUID | None
    answer_source_digest: str | None
    requested_by: UUID
    graph_name: str
    graph_version: str
    graph_thread_id: str
    provider_code: str
    model_code: str
    status: RunStatus
    current_stage: str
    controller_verdict: str | None
    pending_action: str | None
    result_journal_id: UUID | None
    error_code: str | None
    version: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    step_no: int
    node_name: str
    status: str
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_seq: int
    event_type: str
    stage: str
    message_code: str | None
    created_at: datetime
