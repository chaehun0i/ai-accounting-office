from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.companies.application.contracts import CompanyUnitOfWork
from app.intake.domain.canonical_fields import Mapping
from app.intake.domain.entities import Column, Confirmation, Import, Receipt
from app.intake.domain.validation import CanonicalRow, ValidationError
from app.intake.domain.workbook import Workbook


class Imports(Protocol):
    def get(self, *, company_id: UUID, resource_id: UUID) -> Import | None: ...
    def add(
        self, value: Import, workbook: Workbook, mappings: list[Mapping], size: int
    ) -> None: ...
    def columns(self, value: Import) -> list[Column]: ...
    def map(self, value: Import, mappings: list[Mapping], actor: UUID, now: datetime) -> None: ...
    def preview(
        self,
        value: Import,
        digest: str,
        expires: datetime,
        errors: list[ValidationError],
        now: datetime,
    ) -> None: ...
    def errors(self, value: Import) -> list[ValidationError]: ...
    def receipt(self, *, company_id: UUID, import_id: UUID) -> Receipt | None: ...
    def replay(self, company_id: UUID, actor: UUID, key: str) -> Confirmation | None: ...
    def source(self, value: Import, source_id: str) -> str | None: ...
    def confirm(
        self,
        value: Import,
        receipt: Receipt,
        rows: list[CanonicalRow],
        actor: UUID,
        key: str,
        fingerprint: str,
        now: datetime,
    ) -> None: ...


class IntakeUnitOfWork(CompanyUnitOfWork, Protocol):
    @property
    def imports(self) -> Imports: ...
