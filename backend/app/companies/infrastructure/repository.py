from dataclasses import asdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.companies.domain.entities import Company, CompanyAccess
from app.companies.infrastructure.models import (
    CompanyModel,
    MembershipModel,
    RolePermissionModel,
    TenantModel,
)


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _access(self, company: CompanyModel, member: MembershipModel) -> CompanyAccess:
        permissions = tuple(
            self.session.scalars(
                select(RolePermissionModel.permission_code)
                .where(
                    RolePermissionModel.role_code == member.role_code,
                )
                .order_by(RolePermissionModel.permission_code)
            )
        )
        entity = Company(**{key: getattr(company, key) for key in Company.__dataclass_fields__})
        return CompanyAccess(entity, member.role_code, permissions)

    def accessible(
        self, user_id: UUID, company_id: UUID, *, lock: bool = False
    ) -> CompanyAccess | None:
        query = (
            select(CompanyModel, MembershipModel)
            .join(MembershipModel)
            .join(TenantModel)
            .where(
                CompanyModel.id == company_id,
                MembershipModel.user_id == user_id,
                MembershipModel.status == "ACTIVE",
                CompanyModel.status == "ACTIVE",
                TenantModel.status == "ACTIVE",
            )
        )
        if lock:
            query = query.with_for_update(of=[CompanyModel, MembershipModel])
        row = self.session.execute(query).one_or_none()
        return None if row is None else self._access(row[0], row[1])

    def list_accessible(self, user_id: UUID) -> list[CompanyAccess]:
        query = (
            select(CompanyModel, MembershipModel)
            .join(MembershipModel)
            .join(TenantModel)
            .where(
                MembershipModel.user_id == user_id,
                MembershipModel.status == "ACTIVE",
                CompanyModel.status == "ACTIVE",
                TenantModel.status == "ACTIVE",
            )
            .order_by(CompanyModel.company_name, CompanyModel.id)
        )
        return [self._access(company, member) for company, member in self.session.execute(query)]

    def create_tenant(self, tenant_id: UUID, name: str) -> None:
        self.session.add(TenantModel(id=tenant_id, name=name))
        self.session.flush()

    def add(self, company: Company) -> None:
        self.session.add(CompanyModel(**asdict(company)))
        self.session.flush()

    def update(self, company: Company, expected_version: int) -> bool:
        values = asdict(company)
        values.pop("id")
        result = self.session.execute(
            update(CompanyModel)
            .where(
                CompanyModel.id == company.id,
                CompanyModel.version == expected_version,
            )
            .values(**values)
            .returning(CompanyModel.id)
        )
        return result.scalar_one_or_none() is not None

    def membership_status(self, company_id: UUID, user_id: UUID) -> str | None:
        return self.session.scalar(
            select(MembershipModel.status).where(
                MembershipModel.company_id == company_id,
                MembershipModel.user_id == user_id,
            )
        )

    def add_member(self, company_id: UUID, user_id: UUID, role_code: str, now: datetime) -> None:
        self.session.add(
            MembershipModel(
                id=uuid4(),
                company_id=company_id,
                user_id=user_id,
                role_code=role_code,
                joined_at=now,
            )
        )
        self.session.flush()
