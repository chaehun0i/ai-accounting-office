"""Company-scoped mapping queries and immutable change requests."""

import hashlib
import re
from collections.abc import Callable
from uuid import UUID, uuid4

from app.accounting.application.contracts import MasterUnitOfWork
from app.accounting.control_accounts.application.contracts import RequestView
from app.accounting.control_accounts.application.impact import ImpactAssessment
from app.accounting.control_accounts.domain.errors import (
    ControlAccountIdempotencyConflict,
    ControlAccountProtected,
)
from app.accounting.control_accounts.domain.roles import ControlAccountRole
from app.companies.application.service import require_company
from app.contracts.access_errors import (
    InvalidInput,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.identity.users.domain.entities import Principal


class ControlAccountService:
    def __init__(self, factory: Callable[[], MasterUnitOfWork]) -> None:
        self.factory = factory

    def mappings(
        self, actor: Principal, company_id: UUID
    ) -> list[dict[str, str | UUID | int | None]]:
        with self.factory() as uow:
            require_company(uow, actor, company_id, "account.read")
            existing = {row.role: row for row in uow.control_accounts.mappings(company_id)}
            return [
                {
                    "role": role.value,
                    "account_id": existing[role.value].account_id
                    if role.value in existing
                    else None,
                    "version": existing[role.value].version if role.value in existing else 0,
                }
                for role in ControlAccountRole
            ]

    def requests(self, actor: Principal, company_id: UUID) -> list[RequestView]:
        with self.factory() as uow:
            require_company(uow, actor, company_id, "control_account.manage")
            return list(uow.control_accounts.requests(company_id))

    def request(self, actor: Principal, company_id: UUID, request_id: UUID) -> RequestView:
        with self.factory() as uow:
            require_company(uow, actor, company_id, "control_account.manage")
            row = uow.control_accounts.request(company_id, request_id)
            if row is None:
                raise ResourceNotFound()
            return row

    def impact(self, actor: Principal, company_id: UUID, request_id: UUID) -> ImpactAssessment:
        with self.factory() as uow:
            require_company(uow, actor, company_id, "control_account.manage")
            row = uow.control_accounts.request(company_id, request_id)
            if row is None:
                raise ResourceNotFound()
            return uow.control_accounts.impact(
                company_id, row.role, row.current_account_id, row.target_account_id
            )

    def create_request(
        self,
        actor: Principal,
        company_id: UUID,
        *,
        role: str,
        target_account_id: UUID,
        expected_mapping_version: int,
        expected_target_account_version: int,
        key: str,
    ) -> RequestView:
        return self._create_request(
            actor,
            company_id,
            role=role,
            target_account_id=target_account_id,
            expected_mapping_version=expected_mapping_version,
            expected_target_account_version=expected_target_account_version,
            key=key,
        )

    def preview_impact(
        self,
        actor: Principal,
        company_id: UUID,
        *,
        role: str,
        target_account_id: UUID,
        expected_mapping_version: int,
        expected_target_account_version: int,
    ) -> ImpactAssessment:
        if role not in {item.value for item in ControlAccountRole}:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company_id, "control_account.manage")
            mapping = uow.control_accounts.mapping(company_id, role)
            current_id = mapping.account_id if mapping is not None else None
            if (mapping.version if mapping else 0) != expected_mapping_version:
                raise VersionConflict()
            target = uow.control_accounts.account(company_id, target_account_id)
            if target is None:
                raise ResourceNotFound()
            if target.version != expected_target_account_version:
                raise VersionConflict()
            return uow.control_accounts.impact(company_id, role, current_id, target_account_id)

    def _create_request(
        self,
        actor: Principal,
        company_id: UUID,
        *,
        role: str,
        target_account_id: UUID,
        expected_mapping_version: int,
        expected_target_account_version: int,
        key: str,
    ) -> RequestView:
        if (
            role not in {item.value for item in ControlAccountRole}
            or expected_mapping_version < 0
            or expected_target_account_version < 1
        ):
            raise InvalidInput()
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        fingerprint = hashlib.sha256(
            f"{company_id}:{actor.user_id}:{role}:{target_account_id}:{expected_mapping_version}:{expected_target_account_version}".encode()
        ).hexdigest()
        with self.factory() as uow:
            require_company(uow, actor, company_id, "control_account.manage")
            uow.control_accounts.lock_company(company_id)
            previous = uow.control_accounts.request_by_key(company_id, actor.user_id, key)
            if previous is not None:
                if previous.request_fingerprint != fingerprint:
                    raise ControlAccountIdempotencyConflict()
                return previous
            mapping = uow.control_accounts.mapping(company_id, role, lock=True)
            current_id = mapping.account_id if mapping is not None else None
            if (mapping.version if mapping else 0) != expected_mapping_version:
                raise VersionConflict()
            target = uow.control_accounts.account(company_id, target_account_id, lock=True)
            if target is None:
                raise ResourceNotFound()
            if target.version != expected_target_account_version:
                raise VersionConflict()
            if target_account_id == current_id:
                raise StateConflict()
            assessment = uow.control_accounts.impact(
                company_id, role, current_id, target_account_id
            )
            if assessment.blocking:
                raise ControlAccountProtected()
            now = uow.now()
            row = uow.control_accounts.add_request(
                id=uuid4(),
                company_id=company_id,
                role=role,
                current_account_id=current_id,
                target_account_id=target_account_id,
                expected_mapping_version=expected_mapping_version,
                expected_target_account_version=expected_target_account_version,
                impact_digest=assessment.digest,
                status="REQUESTED",
                requester_id=actor.user_id,
                request_key=key,
                request_fingerprint=fingerprint,
                approver_id=None,
                approved_at=None,
                rejected_at=None,
                executed_by_id=None,
                executed_at=None,
                execution_key=None,
                execution_fingerprint=None,
                version=1,
                created_at=now,
                updated_at=now,
            )
            uow.control_accounts.add_event(
                id=uuid4(),
                company_id=company_id,
                request_id=row.id,
                role=role,
                event_type="REQUESTED",
                reason=None,
                actor_id=actor.user_id,
                before_account_id=current_id,
                after_account_id=target_account_id,
                occurred_at=now,
            )
            return row
