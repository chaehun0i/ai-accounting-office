from typing import Protocol
from uuid import UUID

from app.companies.application.contracts import CompanyUnitOfWork
from app.evidence.domain.entities import Evidence


class Evidences(Protocol):
    def get(self, *, company_id: UUID, resource_id: UUID) -> Evidence | None: ...
    def add(self, value: Evidence) -> None: ...


class EvidenceUnitOfWork(CompanyUnitOfWork, Protocol):
    @property
    def evidences(self) -> Evidences: ...
