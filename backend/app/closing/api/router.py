"""기간 상태는 전용 결산 명령만 변경할 수 있습니다."""

from dataclasses import asdict
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.journals.api.router import read as journal_read
from app.accounting.journals.api.schemas import JournalRead
from app.accounting.journals.domain.entities import JournalLine
from app.closing.api.schemas import (
    AdjustmentCreate,
    AdjustmentRead,
    ApprovalDecision,
    ApprovalRead,
    ApprovalRequest,
    Finish,
    Reopen,
    Reversal,
    RunDetail,
    RunRead,
    Start,
    TrialBalanceRead,
)
from app.closing.application.service import ClosingService
from app.contracts.errors import DatabaseUnavailable
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf

router = APIRouter(tags=["월마감"])


def closing(container: Container) -> ClosingService:
    if container.closing is None:
        raise DatabaseUnavailable()
    return container.closing


Service = Annotated[ClosingService, Depends(closing)]


@router.get("/closing/periods")
def periods(actor: Actor, company_id: CompanyScope, service: Service) -> list[dict[str, Any]]:
    return [asdict(period) for period in service.periods(actor, company_id)]


@router.get("/closing/periods/{period_id}/runs", response_model=list[RunRead])
def history(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, Any]]:
    return [asdict(run) for run in service.history(actor, company_id, period_id)]


@router.post("/closing-runs", response_model=RunRead, status_code=201, dependencies=[Depends(csrf)])
def start(
    payload: Start, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> dict[str, Any]:
    return asdict(service.start(actor, company_id, payload.accounting_period_id, key))


@router.get("/closing-runs/{run_id}", response_model=RunDetail)
def detail(
    run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, Any]:
    run, checks, adjustments = service.detail(actor, company_id, run_id)
    return {
        **asdict(run),
        "checks": [asdict(c) for c in checks],
        "adjustments": [asdict(a) for a in adjustments],
    }


@router.get("/closing-runs/{run_id}/approvals", response_model=list[ApprovalRead])
def approvals(
    run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, Any]]:
    return [asdict(approval) for approval in service.approvals(actor, company_id, run_id)]


@router.post(
    "/closing-runs/{run_id}/checks", response_model=RunDetail, dependencies=[Depends(csrf)]
)
def rerun(
    run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> dict[str, Any]:
    service.rerun(actor, company_id, run_id, key)
    return detail(run_id, actor, company_id, service)


@router.post(
    "/closing-runs/{run_id}/adjustments",
    response_model=AdjustmentRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def adjustment(
    run_id: UUID,
    payload: AdjustmentCreate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> dict[str, Any]:
    lines = tuple(
        JournalLine(
            id=uuid4(),
            line_no=index,
            **line.model_dump(exclude={"dimension_value_ids"}),
            dimension_value_ids=tuple(line.dimension_value_ids),
        )
        for index, line in enumerate(payload.lines, 1)
    )
    return asdict(
        service.propose_adjustment(
            actor,
            company_id,
            run_id,
            payload.adjustment_type,
            payload.entry_date,
            payload.description,
            lines,
            payload.auto_reverse,
            payload.scheduled_reversal_date,
            key,
        )
    )


@router.post(
    "/closing-runs/{run_id}/submit", response_model=ApprovalRead, dependencies=[Depends(csrf)]
)
def submit(
    run_id: UUID,
    payload: ApprovalRequest,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> dict[str, Any]:
    return asdict(service.request_approval(actor, company_id, run_id, "CLOSE", payload.reason, key))


@router.post(
    "/closing-approvals/{approval_id}/approve",
    response_model=ApprovalRead,
    dependencies=[Depends(csrf)],
)
def approve(
    approval_id: UUID,
    payload: ApprovalDecision,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> dict[str, Any]:
    return asdict(service.approve(actor, company_id, approval_id, payload.reason, key))


@router.post("/closing-runs/{run_id}/close", response_model=RunRead, dependencies=[Depends(csrf)])
def close(
    run_id: UUID,
    payload: Finish,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> dict[str, Any]:
    return asdict(service.finish(actor, company_id, run_id, payload.approval_id, key))


@router.post(
    "/closing-runs/{run_id}/reopen-request",
    response_model=ApprovalRead,
    dependencies=[Depends(csrf)],
)
def reopen_request(
    run_id: UUID,
    payload: ApprovalRequest,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> dict[str, Any]:
    return asdict(
        service.request_approval(actor, company_id, run_id, "REOPEN", payload.reason, key)
    )


@router.post("/closing-runs/{run_id}/reopen", dependencies=[Depends(csrf)])
def reopen(
    run_id: UUID,
    payload: Reopen,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> dict[str, Any]:
    return asdict(
        service.reopen(actor, company_id, run_id, payload.approval_id, payload.reason, key)
    )


@router.get("/closing-runs/{run_id}/trial-balance", response_model=TrialBalanceRead)
def trial(
    run_id: UUID, stage: str, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, Any]:
    digest, rows = service.adjusted_trial_balance(actor, company_id, run_id, stage)
    return {"stage": stage, "digest": digest, "rows": [asdict(row) for row in rows]}


@router.post(
    "/closing-adjustments/{adjustment_id}/reversal",
    response_model=JournalRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def reversal(
    adjustment_id: UUID,
    payload: Reversal,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> JournalRead:
    return journal_read(
        service.propose_reversal(actor, company_id, adjustment_id, payload.reason, key)
    )
