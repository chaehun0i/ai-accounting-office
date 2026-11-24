from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from app.accounting.api.router import Actor, CompanyScope
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf
from app.reporting.equity.api import Generate, ReviewCommand, Service
from app.reporting.statement_sets.review import StatementSetReviewService
from app.reporting.statement_sets.service import StatementSetService

router = APIRouter(prefix="/financial-statement-sets", tags=["재무제표 세트 승인"])


@router.get("/readiness")
def readiness(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return StatementSetService(service.factory).readiness(actor, company_id, period_id)


@router.get("")
def history(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, object]]:
    return StatementSetService(service.factory).list(actor, company_id, period_id)


@router.post("/generate", status_code=201, dependencies=[Depends(csrf)])
def generate(
    payload: Generate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> dict[str, object]:
    return StatementSetService(service.factory).generate(actor, company_id, payload.period_id, key)


@router.get("/{identifier}")
def detail(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return StatementSetService(service.factory).detail(actor, company_id, identifier)


@router.get("/{identifier}/review")
def review(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return StatementSetReviewService(service).detail(actor, company_id, identifier)


@router.post("/{identifier}/review/{action}", dependencies=[Depends(csrf)])
def transition(
    identifier: UUID,
    action: Literal["request-review", "approve", "reject"],
    payload: ReviewCommand,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> dict[str, object]:
    return StatementSetReviewService(service).transition(
        actor, company_id, identifier, payload.expected_version, action, payload.reason, key
    )
