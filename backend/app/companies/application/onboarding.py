"""회사 초안 승격을 기존 회사 Application 경계에서 처리합니다."""

from dataclasses import replace

from app.companies.application.contracts import CompanyUnitOfWork
from app.companies.application.service import require_company
from app.companies.domain.entities import Company
from app.contracts.access_errors import InvalidInput, VersionConflict
from app.identity.users.domain.entities import Principal


def promote_company(uow: CompanyUnitOfWork, actor: Principal, value: Company) -> None:
    current = require_company(uow, actor, value.id, "company.read").company
    keys = (
        "company_name",
        "business_number",
        "corporation_number",
        "taxpayer_type",
        "opening_date",
        "timezone",
    )
    if all(getattr(current, key) == getattr(value, key) for key in keys):
        return
    require_company(uow, actor, value.id, "company.update")
    if len(value.company_name) > 200 or value.timezone != "Asia/Seoul":
        raise InvalidInput()
    updated = replace(value, version=current.version + 1, updated_at=uow.now())
    if not uow.companies.update(updated, current.version):
        raise VersionConflict()
