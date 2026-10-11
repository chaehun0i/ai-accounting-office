"""회사별 관리차원 변경은 동일 분석축 잠금과 버전 검사 안에서 수행합니다."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from app.accounting.dimensions.application.contracts import DimensionUnitOfWork
from app.accounting.dimensions.domain.entities import Dimension, DimensionValue
from app.accounting.dimensions.domain.rules import TYPES, validate_dates, validate_definition
from app.companies.application.service import require_company
from app.contracts.access_errors import (
    InvalidInput,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.identity.users.domain.entities import Principal


class DimensionService:
    def __init__(self, factory: Callable[[], DimensionUnitOfWork]) -> None:
        self.factory = factory

    def list_dimensions(self, actor: Principal, company: UUID) -> list[Dimension]:
        with self.factory() as uow:
            require_company(uow, actor, company, "dimension.read")
            return uow.dimensions.list_dimensions(company)

    def values(self, actor: Principal, company: UUID, resource: UUID) -> list[DimensionValue]:
        with self.factory() as uow:
            require_company(uow, actor, company, "dimension.read")
            if uow.dimensions.get(company, resource) is None:
                raise ResourceNotFound()
            return uow.dimensions.values(company, resource)

    def create(
        self,
        actor: Principal,
        company: UUID,
        *,
        dimension_code: str,
        name: str,
        dimension_type: str,
        required_policy: str = "OPTIONAL",
    ) -> Dimension:
        validate_definition(dimension_code, name, "ACTIVE")
        if dimension_type not in TYPES or required_policy not in ("OPTIONAL", "REQUIRED"):
            raise InvalidInput()
        now = datetime.now(UTC)
        with self.factory() as uow:
            require_company(uow, actor, company, "dimension.manage")
            if any(
                d.dimension_code == dimension_code for d in uow.dimensions.list_dimensions(company)
            ):
                raise StateConflict()
            value = Dimension(
                id=uuid4(),
                company_id=company,
                dimension_code=dimension_code,
                name=name.strip(),
                dimension_type=dimension_type,
                status="ACTIVE",
                required_policy=required_policy,
                version=1,
                created_at=now,
                updated_at=now,
            )
            uow.dimensions.add(value)
            return value

    def update(
        self,
        actor: Principal,
        company: UUID,
        resource: UUID,
        *,
        expected_version: int,
        name: str,
        status: str,
        required_policy: str,
    ) -> Dimension:
        with self.factory() as uow:
            require_company(uow, actor, company, "dimension.manage")
            current = uow.dimensions.get(company, resource, lock=True)
            if current is None:
                raise ResourceNotFound()
            validate_definition(current.dimension_code, name, status)
            if required_policy not in ("OPTIONAL", "REQUIRED"):
                raise InvalidInput()
            if current.version != expected_version:
                raise VersionConflict()
            value = replace(
                current,
                name=name.strip(),
                status=status,
                required_policy=required_policy,
                version=current.version + 1,
                updated_at=datetime.now(UTC),
            )
            if not uow.dimensions.update(value, expected_version):
                raise VersionConflict()
            return value

    def save_value(
        self,
        actor: Principal,
        company: UUID,
        dimension: UUID,
        *,
        value_code: str,
        name: str,
        parent_value_id: UUID | None = None,
        status: str = "ACTIVE",
        effective_from: date | None = None,
        effective_to: date | None = None,
        resource: UUID | None = None,
        expected_version: int | None = None,
    ) -> DimensionValue:
        validate_definition(value_code, name, status)
        validate_dates(effective_from, effective_to)
        with self.factory() as uow:
            require_company(uow, actor, company, "dimension.manage")
            if uow.dimensions.get(company, dimension, lock=True) is None:
                raise ResourceNotFound()
            values = uow.dimensions.values(company, dimension, lock=True)
            by_id = {v.id: v for v in values}
            current = by_id.get(resource) if resource else None
            if resource and current is None:
                raise ResourceNotFound()
            if current and current.version != expected_version:
                raise VersionConflict()
            if any(v.value_code == value_code and v.id != resource for v in values):
                raise StateConflict()
            parent = parent_value_id
            seen: set[UUID] = set()
            while parent:
                if parent == resource or parent in seen:
                    raise InvalidInput()
                seen.add(parent)
                if parent not in by_id:
                    raise ResourceNotFound()
                parent = by_id[parent].parent_value_id
            now = datetime.now(UTC)
            value = DimensionValue(
                id=resource or uuid4(),
                company_id=company,
                dimension_id=dimension,
                value_code=value_code,
                name=name.strip(),
                parent_value_id=parent_value_id,
                status=status,
                effective_from=effective_from,
                effective_to=effective_to,
                version=current.version + 1 if current else 1,
                created_at=current.created_at if current else now,
                updated_at=now,
            )
            if current:
                if not uow.dimensions.update(value, current.version):
                    raise VersionConflict()
            else:
                uow.dimensions.add(value)
            return value
