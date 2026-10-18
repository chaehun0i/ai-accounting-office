"""Independent approval and execution of a company control account change."""

import hashlib
import re
from collections.abc import Callable
from uuid import UUID, uuid4

from app.accounting.application.contracts import MasterUnitOfWork
from app.accounting.control_accounts.application.contracts import EventView, RequestView
from app.companies.application.service import require_company
from app.contracts.access_errors import (
    AuthorizationDenied,
    InvalidInput,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.identity.users.domain.entities import Principal


class ControlAccountApproval:
    def __init__(self, factory: Callable[[], MasterUnitOfWork]) -> None:
        self.factory = factory

    @staticmethod
    def _current(uow: MasterUnitOfWork, company: UUID, request_id: UUID) -> RequestView:
        # All transitions lock the company first, then the request and the mapping.
        uow.control_accounts.lock_company(company)
        change = uow.control_accounts.request(company, request_id, lock=True)
        if change is None:
            raise ResourceNotFound()
        return change

    @staticmethod
    def _assert_fresh(uow: MasterUnitOfWork, company: UUID, change: RequestView) -> None:
        mapping = uow.control_accounts.mapping(company, change.role, lock=True)
        current_id = mapping.account_id if mapping is not None else None
        current_version = mapping.version if mapping is not None else 0
        if (
            current_id != change.current_account_id
            or current_version != change.expected_mapping_version
        ):
            raise VersionConflict()
        account = uow.accounts.get_locked(company_id=company, resource_id=change.target_account_id)
        if account is None or account.version != change.expected_target_account_version:
            raise VersionConflict()
        assessment = uow.control_accounts.impact(
            company, change.role, change.current_account_id, change.target_account_id
        )
        if assessment.blocking or assessment.digest != change.impact_digest:
            raise VersionConflict()

    @staticmethod
    def _event(
        uow: MasterUnitOfWork,
        change: RequestView,
        actor: UUID,
        event_type: str,
        reason: str | None = None,
    ) -> None:
        uow.control_accounts.add_event(
            id=uuid4(),
            company_id=change.company_id,
            request_id=change.id,
            role=change.role,
            event_type=event_type,
            reason=reason,
            actor_id=actor,
            before_account_id=change.current_account_id,
            after_account_id=change.target_account_id,
            occurred_at=uow.now(),
        )

    def approve(
        self, actor: Principal, company: UUID, request_id: UUID, expected_version: int
    ) -> RequestView:
        with self.factory() as uow:
            require_company(uow, actor, company, "control_account.manage")
            change = self._current(uow, company, request_id)
            if change.version != expected_version:
                raise VersionConflict()
            if change.status != "REQUESTED":
                raise StateConflict()
            if change.requester_id == actor.user_id:
                raise AuthorizationDenied()
            self._assert_fresh(uow, company, change)
            change.status = "APPROVED"
            change.approver_id = actor.user_id
            change.approved_at = uow.now()
            change.updated_at = change.approved_at
            change.version += 1
            self._event(uow, change, actor.user_id, "APPROVED")
            return change

    def reject(
        self,
        actor: Principal,
        company: UUID,
        request_id: UUID,
        expected_version: int,
        reason: str,
    ) -> RequestView:
        if not reason.strip():
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "control_account.manage")
            change = self._current(uow, company, request_id)
            if change.version != expected_version:
                raise VersionConflict()
            if change.status != "REQUESTED":
                raise StateConflict()
            if change.requester_id == actor.user_id:
                raise AuthorizationDenied()
            change.status = "REJECTED"
            change.approver_id = actor.user_id
            change.rejected_at = uow.now()
            change.updated_at = change.rejected_at
            change.version += 1
            self._event(uow, change, actor.user_id, "REJECTED", reason.strip())
            return change

    def execute(
        self,
        actor: Principal,
        company: UUID,
        request_id: UUID,
        expected_version: int,
        key: str,
    ) -> RequestView:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        fingerprint = hashlib.sha256(
            f"{company}:{request_id}:{expected_version}:{actor.user_id}".encode()
        ).hexdigest()
        with self.factory() as uow:
            require_company(uow, actor, company, "control_account.manage")
            change = self._current(uow, company, request_id)
            if change.status == "EXECUTED":
                if (
                    change.execution_key == key
                    and change.execution_fingerprint == fingerprint
                    and change.executed_by_id == actor.user_id
                ):
                    return change
                raise StateConflict()
            if change.version != expected_version:
                raise VersionConflict()
            if change.status != "APPROVED":
                raise StateConflict()
            # The approver may execute, but the requester may never consume an approval.
            if change.requester_id == actor.user_id:
                raise AuthorizationDenied()
            self._assert_fresh(uow, company, change)
            uow.control_accounts.set_mapping(
                company, change.role, change.target_account_id, change.expected_mapping_version
            )
            change.status = "EXECUTED"
            change.executed_by_id = actor.user_id
            change.executed_at = uow.now()
            change.updated_at = change.executed_at
            change.execution_key = key
            change.execution_fingerprint = fingerprint
            change.version += 1
            self._event(uow, change, actor.user_id, "EXECUTED")
            return change

    def events(self, actor: Principal, company: UUID, request_id: UUID) -> list[EventView]:
        with self.factory() as uow:
            require_company(uow, actor, company, "control_account.manage")
            if uow.control_accounts.request(company, request_id) is None:
                raise ResourceNotFound()
            return list(uow.control_accounts.events(company, request_id))
