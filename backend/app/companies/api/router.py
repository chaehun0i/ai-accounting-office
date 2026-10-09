from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.companies.api.schemas import CompanyCreate, CompanyRead, CompanyUpdate
from app.composition import Services
from app.identity.auth.api.dependencies import csrf, principal, services
from app.identity.users.domain.entities import Principal

router = APIRouter(prefix="/companies", tags=["회사"])
Actor = Annotated[Principal, Depends(principal)]
Container = Annotated[Services, Depends(services)]


@router.get("", response_model=list[CompanyRead])
def list_companies(actor: Actor, container: Container) -> list[CompanyRead]:
    return [CompanyRead.from_access(item) for item in container.companies.list(actor)]


@router.post("", response_model=CompanyRead, status_code=201, dependencies=[Depends(csrf)])
def create_company(payload: CompanyCreate, actor: Actor, container: Container) -> CompanyRead:
    return CompanyRead.from_access(container.companies.create(actor, **payload.model_dump()))


@router.get("/{company_id}", response_model=CompanyRead)
def read_company(company_id: UUID, actor: Actor, container: Container) -> CompanyRead:
    return CompanyRead.from_access(container.companies.get(actor, company_id))


@router.patch("/{company_id}", response_model=CompanyRead, dependencies=[Depends(csrf)])
def update_company(
    company_id: UUID, payload: CompanyUpdate, actor: Actor, container: Container
) -> CompanyRead:
    return CompanyRead.from_access(
        container.companies.update(actor, company_id, **payload.model_dump())
    )
