"""실행 조회와 재개 API입니다. 사람 응답은 회계 승인이 아닙니다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.accounting.api.router import Actor, CompanyScope, Container
from app.agents.graphs.bookkeeping import HumanDecision
from app.agents.runtime.service import AgentRuntime
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf
from app.jobs.domain.runtime import EventRead, RunRead, StepRead

router = APIRouter(tags=["회계 제안 실행"])


class StartRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_id: UUID


class AskAccounting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_id: UUID
    question: str = Field(min_length=1, max_length=500)


class ResumeRun(HumanDecision):
    expected_version: int = Field(ge=1)


def runtime(container: Container) -> AgentRuntime:
    if container.agent_runtime is None:
        raise DatabaseUnavailable()
    return container.agent_runtime


Service = Annotated[AgentRuntime, Depends(runtime)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


@router.post("/agent/runs/bookkeeper", response_model=RunRead, dependencies=[Depends(csrf)])
def start(
    payload: StartRun, actor: Actor, company_id: CompanyScope, key: Key, service: Service
) -> RunRead:
    return service.start(actor, company_id, payload.transaction_id, key)


@router.post("/agent/queries/bookkeeper", response_model=RunRead, dependencies=[Depends(csrf)])
def ask(
    payload: AskAccounting, actor: Actor, company_id: CompanyScope, key: Key, service: Service
) -> RunRead:
    return service.ask(actor, company_id, payload.period_id, payload.question, key)


@router.get("/agent/runs/{run_id}", response_model=RunRead)
def get(run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service) -> RunRead:
    return service.audit.get(actor, company_id, run_id)


@router.get("/agent/runs/{run_id}/steps", response_model=list[StepRead])
def steps(run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service) -> list[StepRead]:
    return service.audit.steps(actor, company_id, run_id)


@router.get("/agent/runs/{run_id}/events", response_model=list[EventRead])
def events(
    run_id: UUID,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    after_seq: int = Query(default=0, ge=0),
) -> list[EventRead]:
    return service.audit.events(actor, company_id, run_id, after_seq)


@router.get("/agent/runs/{run_id}/stream")
def stream(
    run_id: UUID,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    after_seq: int = Query(default=0, ge=0),
) -> StreamingResponse:
    # 감사 이벤트를 먼저 조회합니다. 전송 실패는 이미 기록된 실행을 변경하지 않습니다.
    values = service.audit.events(actor, company_id, run_id, after_seq)
    return StreamingResponse(
        (
            f"id: {e.event_seq}\nevent: {e.event_type}\ndata: {e.model_dump_json()}\n\n"
            for e in values
        ),
        media_type="text/event-stream",
    )


@router.post("/agent/runs/{run_id}/resume", response_model=RunRead, dependencies=[Depends(csrf)])
def resume(
    run_id: UUID, payload: ResumeRun, actor: Actor, company_id: CompanyScope, service: Service
) -> RunRead:
    return service.resume(
        actor,
        company_id,
        run_id,
        payload.expected_version,
        HumanDecision(decision=payload.decision),
    )
