from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf
from app.tax.contracts import (
    Period,
    PeriodCreate,
    Preparation,
    Profile,
    ProfileCreate,
    Vat,
    VatCreate,
    Withholding,
    WithholdingCreate,
)
from app.tax.service import TaxService

router = APIRouter(prefix="/tax", tags=["세무 신고자료 준비"])


def tax(container: Container) -> TaxService:
    if container.tax is None:
        raise DatabaseUnavailable()
    return container.tax


Service = Annotated[TaxService, Depends(tax)]


@router.get("/profiles", response_model=tuple[Profile, ...])
def profiles(actor: Actor, company_id: CompanyScope, service: Service) -> tuple[Profile, ...]:
    return service.profiles(actor, company_id)


@router.post("/profiles", response_model=Profile, status_code=201, dependencies=[Depends(csrf)])
def profile(
    payload: ProfileCreate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> Profile:
    return service.create_profile(actor, company_id, payload, key)


@router.get("/periods", response_model=tuple[Period, ...])
def periods(actor: Actor, company_id: CompanyScope, service: Service) -> tuple[Period, ...]:
    return service.periods(actor, company_id)


@router.post("/periods", response_model=Period, status_code=201, dependencies=[Depends(csrf)])
def period(
    payload: PeriodCreate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> Period:
    return service.create_period(actor, company_id, payload, key)


@router.post(
    "/periods/{period_id}/vat", response_model=Vat, status_code=201, dependencies=[Depends(csrf)]
)
def vat(
    period_id: UUID,
    payload: VatCreate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> Vat:
    return service.record_vat(actor, company_id, period_id, payload, key)


@router.post(
    "/periods/{period_id}/withholding",
    response_model=Withholding,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def withholding(
    period_id: UUID,
    payload: WithholdingCreate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> Withholding:
    return service.record_withholding(actor, company_id, period_id, payload, key)


@router.get("/periods/{period_id}/preparation", response_model=Preparation)
def preparation(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> Preparation:
    return service.preparation(actor, company_id, period_id)
