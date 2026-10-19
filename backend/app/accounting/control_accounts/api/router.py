from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.control_accounts.api.approval_schemas import ChangeRequestRead
from app.accounting.control_accounts.api.schemas import ImpactRead, MappingRead, RequestCreate
from app.accounting.control_accounts.application.service import ControlAccountService
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf

router = APIRouter(tags=["Control Account Roles"])


def core_service(container: Container) -> ControlAccountService:
    if container.accounting is None:
        raise DatabaseUnavailable()
    return ControlAccountService(container.accounting.factory)


Core = Annotated[ControlAccountService, Depends(core_service)]
Key = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$"),
]


@router.get("/control-account-roles", response_model=list[MappingRead])
def mappings(actor: Actor, company_id: CompanyScope, service: Core) -> list[MappingRead]:
    return [MappingRead.model_validate(row) for row in service.mappings(actor, company_id)]


@router.get("/control-account-roles/requests", response_model=list[ChangeRequestRead])
def requests(actor: Actor, company_id: CompanyScope, service: Core) -> list[ChangeRequestRead]:
    return [ChangeRequestRead.model_validate(row) for row in service.requests(actor, company_id)]


@router.get("/control-account-roles/requests/{request_id}", response_model=ChangeRequestRead)
def request(
    request_id: UUID, actor: Actor, company_id: CompanyScope, service: Core
) -> ChangeRequestRead:
    return ChangeRequestRead.model_validate(service.request(actor, company_id, request_id))


@router.get("/control-account-roles/requests/{request_id}/impact", response_model=ImpactRead)
def impact(request_id: UUID, actor: Actor, company_id: CompanyScope, service: Core) -> ImpactRead:
    value = service.impact(actor, company_id, request_id)
    return ImpactRead.model_validate(
        {"digest": value.digest, "blocking": value.blocking, "facts": value.facts}
    )


@router.post(
    "/control-account-roles/impact", response_model=ImpactRead, dependencies=[Depends(csrf)]
)
def preview_impact(
    payload: RequestCreate,
    actor: Actor,
    company_id: CompanyScope,
    service: Core,
) -> ImpactRead:
    value = service.preview_impact(actor, company_id, **payload.model_dump())
    return ImpactRead.model_validate(
        {"digest": value.digest, "blocking": value.blocking, "facts": value.facts}
    )


@router.post(
    "/control-account-roles/requests",
    response_model=ChangeRequestRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def create_request(
    payload: RequestCreate,
    actor: Actor,
    company_id: CompanyScope,
    key: Key,
    service: Core,
) -> ChangeRequestRead:
    return ChangeRequestRead.model_validate(
        service.create_request(actor, company_id, key=key, **payload.model_dump())
    )
