from collections.abc import Callable
from dataclasses import replace
from datetime import date
from uuid import UUID, uuid4

from app.companies.application.contracts import CompanyUnitOfWork
from app.companies.domain.entities import Company, CompanyAccess
from app.contracts.access_errors import (
    AuthenticationRequired,
    AuthorizationDenied,
    ResourceNotFound,
    VersionConflict,
)
from app.identity.users.domain.entities import Principal


def validate_principal(uow: CompanyUnitOfWork, principal: Principal) -> None:
    user = uow.users.get(principal.user_id, lock=True)
    session = uow.sessions.get(principal.user_id, principal.session_id)
    if (
        user is None
        or user.status != "ACTIVE"
        or session is None
        or session.revoked_at
        or session.expires_at <= uow.now()
    ):
        raise AuthenticationRequired()


def require_company(
    uow: CompanyUnitOfWork, principal: Principal, company_id: UUID, permission: str
) -> CompanyAccess:
    validate_principal(uow, principal)
    access = uow.companies.accessible(principal.user_id, company_id, lock=True)
    if access is None:
        raise ResourceNotFound()
    if permission not in access.permissions:
        raise AuthorizationDenied()
    return access


class CompanyService:
    def __init__(
        self,
        factory: Callable[[], CompanyUnitOfWork],
        prepare_accounts: Callable[[CompanyUnitOfWork, UUID], None] | None = None,
    ) -> None:
        self.factory = factory
        self.prepare_accounts = prepare_accounts

    def list(self, principal: Principal) -> list[CompanyAccess]:
        with self.factory() as uow:
            validate_principal(uow, principal)
            return [
                access
                for access in uow.companies.list_accessible(principal.user_id)
                if "company.read" in access.permissions
            ]

    def get(self, principal: Principal, company_id: UUID) -> CompanyAccess:
        with self.factory() as uow:
            return require_company(uow, principal, company_id, "company.read")

    def create(
        self,
        principal: Principal,
        *,
        company_name: str,
        business_number: str,
        taxpayer_type: str,
        opening_date: date,
        address: str,
        corporation_number: str | None = None,
    ) -> CompanyAccess:
        with self.factory() as uow:
            validate_principal(uow, principal)
            now = uow.now()
            company = Company(
                uuid4(),
                uuid4(),
                company_name,
                business_number,
                taxpayer_type,
                opening_date,
                address,
                corporation_number,
                created_at=now,
                updated_at=now,
            )
            uow.companies.create_tenant(company.tenant_id, company_name)
            uow.companies.add(company)
            uow.companies.add_member(company.id, principal.user_id, "OWNER", now)
            if self.prepare_accounts is not None:
                self.prepare_accounts(uow, company.id)
            access = uow.companies.accessible(principal.user_id, company.id)
            assert access is not None
            return access

    def update(
        self,
        principal: Principal,
        company_id: UUID,
        expected_version: int,
        *,
        company_name: str | None = None,
        address: str | None = None,
    ) -> CompanyAccess:
        with self.factory() as uow:
            access = require_company(uow, principal, company_id, "company.update")
            company = replace(
                access.company,
                company_name=company_name or access.company.company_name,
                address=address or access.company.address,
                version=expected_version + 1,
                updated_at=uow.now(),
            )
            if not uow.companies.update(company, expected_version):
                raise VersionConflict()
            return CompanyAccess(company, access.role_code, access.permissions)
