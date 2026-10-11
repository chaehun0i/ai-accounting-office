"""도구 정의와 실행 컨텍스트의 단일 계약입니다."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.identity.users.domain.entities import Principal


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Empty(Input):
    pass


class ResourceInput(Input):
    transaction_id: UUID


class SearchInput(Input):
    query_text: str = Field(default="", max_length=100)
    account_type: Literal["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"] | None = None
    limit: int = Field(default=20, ge=1, le=20)


class AsOfInput(Input):
    as_of: date


class PeriodInput(Input):
    period_id: UUID


class LedgerInput(Input):
    account_id: UUID
    date_from: date
    date_to: date


class Result[D](BaseModel):
    status: Literal["SUCCEEDED"] = "SUCCEEDED"
    as_of: date
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[UUID] = Field(default_factory=list)
    data: D


@dataclass(frozen=True)
class ToolContext:
    principal: Principal
    company_id: UUID
    run_id: UUID | None = None
    step_id: UUID | None = None
    invocation_id: UUID | None = None


@dataclass(frozen=True)
class ToolDefinition:
    tool_code: str
    description: str
    required_permission: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    handler: Callable[[ToolContext, BaseModel], BaseModel]
    version: str = "1"
    tool_class: Literal["READ", "PROPOSE", "COMMAND", "EXTERNAL"] = "READ"
    side_effect_level: Literal["NONE", "PROPOSAL"] = "NONE"
    timeout_seconds: int = 10
