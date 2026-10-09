from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.companies.api.schemas import CompanyRead
from app.composition import Services
from app.identity.auth.api.dependencies import csrf, principal, services
from app.identity.auth.api.schemas import CommandResult
from app.identity.users.domain.entities import Principal

router = APIRouter(tags=["회사 초대"], dependencies=[Depends(csrf)])
Actor = Annotated[Principal, Depends(principal)]
Container = Annotated[Services, Depends(services)]


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role_code: Literal[
        "OWNER",
        "ADMIN",
        "ACCOUNTANT",
        "REVIEWER",
        "TAX_ACCOUNTANT",
        "TAX_REVIEWER",
        "VIEWER",
        "AUDITOR",
    ]


class InvitationRead(BaseModel):
    id: UUID
    company_id: UUID
    email: EmailStr
    role_code: str
    expires_at: datetime
    status: str
    invite_token: str = Field(repr=False)


@router.post("/companies/{company_id}/invitations", response_model=InvitationRead, status_code=201)
def create_invitation(
    company_id: UUID, payload: InvitationCreate, actor: Actor, container: Container
) -> InvitationRead:
    result = container.invitations.create(actor, company_id, str(payload.email), payload.role_code)
    invitation = result.invitation
    return InvitationRead(
        id=invitation.id,
        company_id=company_id,
        email=invitation.email,
        role_code=invitation.role_code,
        expires_at=invitation.expires_at,
        status=invitation.status,
        invite_token=result.token,
    )


@router.post("/invitations/{token}/accept", response_model=CompanyRead)
def accept_invitation(
    token: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{43}$")], actor: Actor, container: Container
) -> CompanyRead:
    return CompanyRead.from_access(container.invitations.accept(actor, token))


@router.delete("/companies/{company_id}/invitations/{invitation_id}", response_model=CommandResult)
def revoke_invitation(
    company_id: UUID, invitation_id: UUID, actor: Actor, container: Container
) -> CommandResult:
    container.invitations.revoke(actor, company_id, invitation_id)
    return CommandResult()
