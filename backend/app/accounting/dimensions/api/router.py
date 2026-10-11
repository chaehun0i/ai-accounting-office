from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.dimensions.api.schemas import (
    DimensionCreate,
    DimensionRead,
    DimensionUpdate,
    ValueCreate,
    ValueRead,
    ValueUpdate,
)
from app.accounting.dimensions.application.service import DimensionService
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf

router = APIRouter(prefix="/accounting/dimensions", tags=["관리차원"])


def dimensions(container: Container) -> DimensionService:
    if container.dimensions is None:
        raise DatabaseUnavailable()
    return container.dimensions


Service = Annotated[DimensionService, Depends(dimensions)]


@router.get("", response_model=list[DimensionRead])
def listing(actor: Actor, company_id: CompanyScope, service: Service) -> list[DimensionRead]:
    return [
        DimensionRead.model_validate(asdict(v)) for v in service.list_dimensions(actor, company_id)
    ]


@router.post("", response_model=DimensionRead, status_code=201, dependencies=[Depends(csrf)])
def create(
    payload: DimensionCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> DimensionRead:
    return DimensionRead.model_validate(
        asdict(service.create(actor, company_id, **payload.model_dump()))
    )


@router.patch("/{resource_id}", response_model=DimensionRead, dependencies=[Depends(csrf)])
def update(
    resource_id: UUID,
    payload: DimensionUpdate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> DimensionRead:
    return DimensionRead.model_validate(
        asdict(service.update(actor, company_id, resource_id, **payload.model_dump()))
    )


@router.get("/{resource_id}/values", response_model=list[ValueRead])
def values(
    resource_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[ValueRead]:
    return [
        ValueRead.model_validate(asdict(v)) for v in service.values(actor, company_id, resource_id)
    ]


@router.post(
    "/{resource_id}/values", response_model=ValueRead, status_code=201, dependencies=[Depends(csrf)]
)
def create_value(
    resource_id: UUID,
    payload: ValueCreate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> ValueRead:
    return ValueRead.model_validate(
        asdict(service.save_value(actor, company_id, resource_id, **payload.model_dump()))
    )


@router.patch(
    "/{resource_id}/values/{value_id}", response_model=ValueRead, dependencies=[Depends(csrf)]
)
def update_value(
    resource_id: UUID,
    value_id: UUID,
    payload: ValueUpdate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> ValueRead:
    return ValueRead.model_validate(
        asdict(
            service.save_value(
                actor, company_id, resource_id, resource=value_id, **payload.model_dump()
            )
        )
    )
