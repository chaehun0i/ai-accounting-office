from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid4

from app.companies.application.service import require_company, validate_principal
from app.companies.domain.entities import CompanyAccess
from app.companies.domain.permissions import ROLES
from app.contracts.access_errors import (
    AuthorizationDenied,
    InvalidInput,
    ResourceNotFound,
    StateConflict,
)
from app.core.security import digest, random_token
from app.identity.invitations.application.contracts import Invitation, InvitationUnitOfWork
from app.identity.users.domain.entities import Principal, normalize_email


@dataclass(frozen=True)
class InvitationResult:
    invitation: Invitation = field(repr=False)
    token: str = field(repr=False)


class InvitationService:
    def __init__(self, factory: Callable[[], InvitationUnitOfWork]) -> None:
        self.factory = factory

    def create(
        self, principal: Principal, company_id: UUID, email: str, role_code: str
    ) -> InvitationResult:
        if role_code not in ROLES:
            raise InvalidInput()
        email = normalize_email(email)
        with self.factory() as uow:
            access = require_company(uow, principal, company_id, "company.members.manage")
            if role_code == "OWNER" and access.role_code != "OWNER":
                raise AuthorizationDenied()
            now = uow.now()
            if uow.invitations.pending(company_id, email, now):
                raise StateConflict()
            token = random_token()
            invitation = Invitation(
                uuid4(),
                company_id,
                email,
                role_code,
                digest(token),
                principal.user_id,
                now + timedelta(days=7),
                now,
            )
            uow.invitations.add(invitation)
            return InvitationResult(invitation, token)

    def accept(self, principal: Principal, token: str) -> CompanyAccess:
        with self.factory() as uow:
            validate_principal(uow, principal)
            invitation = uow.invitations.for_token(digest(token), principal.email)
            if invitation is None:
                raise ResourceNotFound()
            now = uow.now()
            if invitation.status != "PENDING" or invitation.expires_at <= now:
                raise StateConflict()
            status = uow.companies.membership_status(invitation.company_id, principal.user_id)
            if status == "REVOKED":
                raise AuthorizationDenied()
            if status is not None:
                raise StateConflict()
            uow.companies.add_member(
                invitation.company_id, principal.user_id, invitation.role_code, now
            )
            invitation.status = "ACCEPTED"
            invitation.accepted_at, invitation.accepted_by = now, principal.user_id
            uow.invitations.save(invitation)
            access = uow.companies.accessible(principal.user_id, invitation.company_id)
            assert access is not None
            return access

    def revoke(self, principal: Principal, company_id: UUID, invitation_id: UUID) -> None:
        with self.factory() as uow:
            require_company(uow, principal, company_id, "company.members.manage")
            invitation = uow.invitations.get(company_id, invitation_id)
            if invitation is None:
                raise ResourceNotFound()
            if invitation.status != "PENDING":
                raise StateConflict()
            invitation.status = "REVOKED"
            uow.invitations.save(invitation)
