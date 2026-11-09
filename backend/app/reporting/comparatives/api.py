"""Company-scoped comparative financial statement endpoints."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf
from app.reporting.comparatives.service import ComparativeStatementsService

router = APIRouter(prefix="/financial-statements/comparatives", tags=["비교 재무제표"])


def service_from(container: Container) -> ComparativeStatementsService:
    if container.comparative_statements is None:
        raise DatabaseUnavailable()
    return container.comparative_statements


Service = Annotated[ComparativeStatementsService, Depends(service_from)]


class Generate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_id: UUID
    comparison_period_id: UUID


class ReclassificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement_type: Literal["BALANCE_SHEET", "INCOME_STATEMENT"]
    from_line_code: str = Field(min_length=1, max_length=40)
    to_line_code: str = Field(min_length=1, max_length=40)
    amount: Decimal = Field(max_digits=28, decimal_places=4)
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class Reject(Transition):
    reason: str = Field(min_length=1, max_length=1000)


@router.get("/readiness")
def readiness(
    period_id: UUID,
    comparison_period_id: UUID,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.readiness(actor, company_id, period_id, comparison_period_id)


@router.post("", status_code=201, dependencies=[Depends(csrf)])
def generate(
    payload: Generate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> dict[str, object]:
    return service.generate(actor, company_id, payload.period_id, payload.comparison_period_id, key)


@router.get("")
def list_snapshots(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, object]]:
    return service.list(actor, company_id, period_id)


@router.get("/{snapshot_id}")
def detail(
    snapshot_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return service.detail(actor, company_id, snapshot_id)


@router.get("/{snapshot_id}/sources")
def sources(
    snapshot_id: UUID,
    statement_type: Literal["BALANCE_SHEET", "INCOME_STATEMENT"],
    line_code: str,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.sources(actor, company_id, snapshot_id, statement_type, line_code)


@router.post("/{snapshot_id}/reclassifications", dependencies=[Depends(csrf)])
def reclassify(
    snapshot_id: UUID,
    payload: ReclassificationCreate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.reclassify(
        actor,
        company_id,
        snapshot_id,
        statement_type=payload.statement_type,
        from_line_code=payload.from_line_code,
        to_line_code=payload.to_line_code,
        amount=payload.amount,
        reason=payload.reason,
        expected_version=payload.expected_version,
    )


@router.post("/{snapshot_id}/request-review", dependencies=[Depends(csrf)])
def request_review(
    snapshot_id: UUID,
    payload: Transition,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.request_review(actor, company_id, snapshot_id, payload.expected_version)


@router.post("/{snapshot_id}/approve", dependencies=[Depends(csrf)])
def approve(
    snapshot_id: UUID,
    payload: Transition,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.approve(actor, company_id, snapshot_id, payload.expected_version)


@router.post("/{snapshot_id}/reject", dependencies=[Depends(csrf)])
def reject(
    snapshot_id: UUID,
    payload: Reject,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.reject(actor, company_id, snapshot_id, payload.expected_version, payload.reason)
