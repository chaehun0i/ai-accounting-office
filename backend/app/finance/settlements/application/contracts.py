"""Application 계약은 Session이나 ORM 타입을 노출하지 않습니다."""

from datetime import date
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.accounting.ledger.application.service import ReportUnitOfWork
from app.approvals.application.contracts import AccountingUnitOfWork
from app.finance.receivables.domain.entities import Obligation
from app.finance.settlements.domain.entities import Allocation, Settlement


class Obligations(Protocol):
    def get(
        self, company_id: UUID, resource_id: UUID, as_of: date, *, lock: bool = False
    ) -> Obligation | None: ...
    def list(self, company_id: UUID, as_of: date) -> list[Obligation]: ...
    def origin(self, company: UUID, journal: UUID, line_no: int) -> Obligation | None: ...
    def add(
        self,
        company: UUID,
        journal: UUID,
        line_no: int,
        counterparty: UUID,
        account: UUID,
        amount: Decimal,
        due: date,
    ) -> UUID: ...
    def refresh(self, company: UUID, resource: UUID) -> None: ...


class Settlements(Protocol):
    def origin(self, company: UUID, journal: UUID) -> UUID | None: ...
    def get(
        self, company_id: UUID, resource_id: UUID, *, lock: bool = False
    ) -> Settlement | None: ...
    def list(self, company: UUID, target: UUID | None = None) -> list[Settlement]: ...
    def add(self, value: Settlement, actor: UUID) -> None: ...
    def replace_allocations(self, value: Settlement, lines: tuple[Allocation, ...]) -> None: ...
    def confirm(self, value: Settlement) -> None: ...
    def replay(
        self, company: UUID, actor: UUID, command: str, key: str, fingerprint: str
    ) -> UUID | None: ...
    def receipt(
        self,
        company: UUID,
        actor: UUID,
        command: str,
        key: str,
        fingerprint: str,
        value: Settlement,
    ) -> None: ...


class FinanceUnitOfWork(AccountingUnitOfWork, ReportUnitOfWork, Protocol):
    def obligations(self, kind: str) -> Obligations: ...
    def settlements(self, kind: str) -> Settlements: ...
    def lock_command(self, company: UUID, actor: UUID, command: str, key: str) -> None: ...
