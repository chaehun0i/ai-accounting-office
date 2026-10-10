from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.accounting.journals.application.contracts import JournalUnitOfWork
from app.approvals.domain.entities import Approval


class Governance(Protocol):
    def approval(self, company: UUID, resource: UUID) -> Approval | None: ...
    def save_approval(self, value: Approval) -> None: ...
    def replay(
        self, company: UUID, actor: UUID, command: str, key: str, fingerprint: str
    ) -> UUID | None: ...
    def record(
        self,
        company: UUID,
        actor: UUID,
        command: str,
        key: str,
        fingerprint: str,
        journal: UUID,
        version: int,
        now: datetime,
    ) -> None: ...
    def audit(
        self,
        company: UUID,
        actor: UUID,
        command: str,
        journal: UUID,
        request_id: str,
        before: str,
        after: str,
        now: datetime,
    ) -> None: ...


class AccountingUnitOfWork(JournalUnitOfWork, Protocol):
    @property
    def governance(self) -> Governance: ...
