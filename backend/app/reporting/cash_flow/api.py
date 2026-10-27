"""현금흐름표 범위·분류 설정과 CLOSED 기간 사전 점검 API."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf
from app.reporting.cash_flow.service import CashFlowService

router = APIRouter(prefix="/cash-flow", tags=["현금흐름표 사전 점검"])


def cash_flow(container: Container) -> CashFlowService:
    if container.cash_flow is None:
        raise DatabaseUnavailable()
    return container.cash_flow


Service = Annotated[CashFlowService, Depends(cash_flow)]


class CashScopeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    scope_type: Literal["CASH", "CASH_EQUIVALENT"]
    effective_from: date


class CashScopeRead(CashScopeCreate):
    id: UUID
    effective_to: date | None
    version: int


class ClassificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    activity_type: Literal["OPERATING", "INVESTING", "FINANCING", "EXCHANGE_EFFECT"]
    line_code: str
    effective_from: date


class ClassificationRead(ClassificationCreate):
    id: UUID
    effective_to: date | None
    version: int


class PreflightIssueRead(BaseModel):
    code: str
    journal_id: UUID | None


class PreflightRead(BaseModel):
    period_id: UUID
    close_version: int
    source_digest: str
    mapping_digest: str
    opening_cash: Decimal
    closing_cash: Decimal
    net_cash_movement: Decimal
    net_operating: Decimal
    net_investing: Decimal
    net_financing: Decimal
    exchange_effect: Decimal
    classified_journal_count: int
    issues: tuple[PreflightIssueRead, ...]
    ready: bool


class AllocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journal_id: UUID
    cash_line_id: UUID
    counterpart_line_id: UUID
    evidence_id: UUID
    amount: Decimal


class AllocationRead(AllocationCreate):
    id: UUID
    version: int
    replaces_id: UUID | None


class AllocationRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal
    evidence_id: UUID


class CashEventRead(BaseModel):
    journal_id: UUID
    cash_line_id: UUID
    cash_account_id: UUID
    counterpart_line_id: UUID
    counterpart_account_id: UUID
    activity_type: str
    line_code: str
    cash_inflow: Decimal
    cash_outflow: Decimal
    classification_id: UUID
    evidence_id: UUID | None


@router.get("/cash-scope", response_model=list[CashScopeRead])
def scopes(actor: Actor, company_id: CompanyScope, service: Service) -> list[CashScopeRead]:
    return [
        CashScopeRead.model_validate(asdict(item)) for item in service.scopes(actor, company_id)
    ]


@router.post(
    "/cash-scope", response_model=CashScopeRead, status_code=201, dependencies=[Depends(csrf)]
)
def map_cash(
    payload: CashScopeCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> CashScopeRead:
    return CashScopeRead.model_validate(
        asdict(service.map_cash(actor, company_id, **payload.model_dump()))
    )


@router.get("/classifications", response_model=list[ClassificationRead])
def classifications(
    actor: Actor, company_id: CompanyScope, service: Service
) -> list[ClassificationRead]:
    return [
        ClassificationRead.model_validate(asdict(item))
        for item in service.classifications(actor, company_id)
    ]


@router.post(
    "/classifications",
    response_model=ClassificationRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def map_activity(
    payload: ClassificationCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> ClassificationRead:
    return ClassificationRead.model_validate(
        asdict(service.map_activity(actor, company_id, **payload.model_dump()))
    )


@router.get("/preflight", response_model=PreflightRead)
def preflight(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> PreflightRead:
    return PreflightRead.model_validate(asdict(service.preflight(actor, company_id, period_id)))


@router.post(
    "/allocations", response_model=AllocationRead, status_code=201, dependencies=[Depends(csrf)]
)
def allocate(
    payload: AllocationCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> AllocationRead:
    return AllocationRead.model_validate(
        asdict(service.allocate(actor, company_id, **payload.model_dump()))
    )


@router.put(
    "/allocations/{allocation_id}",
    response_model=AllocationRead,
    dependencies=[Depends(csrf)],
)
def revise_allocation(
    allocation_id: UUID,
    payload: AllocationRevision,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> AllocationRead:
    return AllocationRead.model_validate(
        asdict(service.revise_allocation(actor, company_id, allocation_id, **payload.model_dump()))
    )


@router.get("/allocations", response_model=list[AllocationRead])
def allocation_history(
    journal_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[AllocationRead]:
    return [
        AllocationRead.model_validate(asdict(item))
        for item in service.allocation_history(actor, company_id, journal_id)
    ]


@router.get("/events", response_model=list[CashEventRead])
def events(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[CashEventRead]:
    return [
        CashEventRead.model_validate(asdict(item))
        for item in service.events(actor, company_id, period_id)
    ]
