"""Application boundary for company-scoped control account persistence."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.accounting.control_accounts.application.impact import ImpactAssessment


class MappingView(Protocol):
    role: str
    account_id: UUID
    version: int


class AccountView(Protocol):
    id: UUID
    version: int
    status: str
    posting_allowed: bool
    account_type: str


class RequestView(Protocol):
    id: UUID
    company_id: UUID
    role: str
    current_account_id: UUID | None
    target_account_id: UUID
    expected_mapping_version: int
    expected_target_account_version: int
    impact_digest: str
    status: str
    requester_id: UUID
    request_key: str
    request_fingerprint: str
    approver_id: UUID | None
    approved_at: datetime | None
    rejected_at: datetime | None
    executed_by_id: UUID | None
    executed_at: datetime | None
    execution_key: str | None
    execution_fingerprint: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class EventView(Protocol):
    id: UUID
    company_id: UUID
    request_id: UUID
    role: str
    event_type: str
    reason: str | None
    actor_id: UUID
    before_account_id: UUID | None
    after_account_id: UUID | None
    occurred_at: datetime


class ControlAccounts(Protocol):
    def lock_company(self, company_id: UUID) -> None: ...
    def mappings(self, company_id: UUID) -> Sequence[MappingView]: ...
    def mapping(self, company_id: UUID, role: str, lock: bool = False) -> MappingView | None: ...
    def request(
        self, company_id: UUID, request_id: UUID, lock: bool = False
    ) -> RequestView | None: ...
    def requests(self, company_id: UUID) -> Sequence[RequestView]: ...
    def request_by_key(
        self, company_id: UUID, requester_id: UUID, key: str
    ) -> RequestView | None: ...
    def account(
        self, company_id: UUID, account_id: UUID, lock: bool = False
    ) -> AccountView | None: ...
    def impact(
        self, company_id: UUID, role: str, current_account_id: UUID | None, target_account_id: UUID
    ) -> ImpactAssessment: ...
    def reference_count(self, code: str, company_id: UUID, account_id: UUID) -> int: ...
    def add_request(self, **values: Any) -> RequestView: ...
    def add_event(self, **values: Any) -> None: ...
    def events(self, company_id: UUID, request_id: UUID) -> Sequence[EventView]: ...
    def set_mapping(
        self, company_id: UUID, role: str, target_account_id: UUID, expected_version: int
    ) -> MappingView: ...
