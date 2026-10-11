from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.finance.invoices.domain.entities import Document, DocumentType
from app.finance.settlements.application.contracts import FinanceUnitOfWork


class Documents(Protocol):
    def get(
        self, company: UUID, kind: DocumentType, resource: UUID, *, lock: bool = False
    ) -> Document | None: ...
    def list(self, company: UUID, kind: DocumentType) -> list[Document]: ...
    def source(
        self, company: UUID, kind: DocumentType, system: str, source_id: str
    ) -> Document | None: ...
    def save(self, value: Document, original_version: int | None = None) -> None: ...
    def original_version(self, company: UUID, resource: UUID) -> int: ...
    def replay(
        self, company: UUID, actor: UUID, command: str, key: str, fingerprint: str
    ) -> UUID | None: ...
    def event(
        self,
        value: Document,
        actor: UUID,
        command: str,
        key: str,
        fingerprint: str,
        before: str,
        now: datetime,
    ) -> None: ...
    def lock_counterparty(self, company: UUID, resource: UUID) -> None: ...


class DocumentUnitOfWork(FinanceUnitOfWork, Protocol):
    @property
    def documents(self) -> Documents: ...
