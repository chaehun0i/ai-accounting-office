from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.control_accounts.api.approval_schemas import (
    ApprovalCommand,
    ChangeEventRead,
    ChangeRequestRead,
    RejectionCommand,
)
from app.accounting.control_accounts.application.approval import ControlAccountApproval
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf

router = APIRouter(tags=["Control Account Roles"])


def approval_service(container: Container) -> ControlAccountApproval:
    if container.accounting is None:
        raise DatabaseUnavailable()
    return ControlAccountApproval(container.accounting.factory)


Approval = Annotated[ControlAccountApproval, Depends(approval_service)]


@router.post(
    "/control-account-roles/requests/{request_id}/approve",
    response_model=ChangeRequestRead,
    dependencies=[Depends(csrf)],
)
def approve(
    request_id: UUID,
    payload: ApprovalCommand,
    actor: Actor,
    company_id: CompanyScope,
    service: Approval,
) -> ChangeRequestRead:
    return ChangeRequestRead.model_validate(
        service.approve(actor, company_id, request_id, payload.expected_version)
    )


@router.post(
    "/control-account-roles/requests/{request_id}/reject",
    response_model=ChangeRequestRead,
    dependencies=[Depends(csrf)],
)
def reject(
    request_id: UUID,
    payload: RejectionCommand,
    actor: Actor,
    company_id: CompanyScope,
    service: Approval,
) -> ChangeRequestRead:
    return ChangeRequestRead.model_validate(
        service.reject(actor, company_id, request_id, payload.expected_version, payload.reason)
    )


@router.post(
    "/control-account-roles/requests/{request_id}/execute",
    response_model=ChangeRequestRead,
    dependencies=[Depends(csrf)],
)
def execute(
    request_id: UUID,
    payload: ApprovalCommand,
    actor: Actor,
    company_id: CompanyScope,
    service: Approval,
    key: Annotated[str, Header(alias="Idempotency-Key")],
) -> ChangeRequestRead:
    return ChangeRequestRead.model_validate(
        service.execute(actor, company_id, request_id, payload.expected_version, key)
    )


@router.get(
    "/control-account-roles/requests/{request_id}/events", response_model=list[ChangeEventRead]
)
def events(
    request_id: UUID, actor: Actor, company_id: CompanyScope, service: Approval
) -> list[ChangeEventRead]:
    return [
        ChangeEventRead.model_validate(row) for row in service.events(actor, company_id, request_id)
    ]
