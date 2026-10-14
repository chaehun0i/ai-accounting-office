from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.closing.application.contracts import ClosingUnitOfWork
from app.reporting.financial_statements.domain.entities import (
    SourceLine,
    StatementSet,
    StatementView,
)


class StatementStore(Protocol):
    def active_taxonomy(self, as_of: date) -> tuple[UUID, int] | None: ...
    def line_ids(self, taxonomy: UUID) -> dict[str, UUID]: ...
    def mappings(
        self, company: UUID, taxonomy: UUID, as_of: date
    ) -> list[tuple[UUID, str, int]]: ...
    def add_mapping(
        self, company: UUID, taxonomy: UUID, account: UUID, line: UUID, effective_from: date
    ) -> None: ...
    def set_for_source(
        self,
        company: UUID,
        period: UUID,
        close_version: int,
        taxonomy: UUID,
        source: str,
        mapping: str,
    ) -> StatementSet | None: ...
    def set(self, company: UUID, identifier: UUID) -> StatementSet | None: ...
    def sets(self, company: UUID, period: UUID) -> list[StatementSet]: ...
    def statement(self, company: UUID, set_id: UUID, kind: str) -> StatementView | None: ...
    def sources(self, company: UUID, statement_line: UUID) -> tuple[SourceLine, ...]: ...
    def replay(self, company: UUID, actor: UUID, key: str, fingerprint: str) -> UUID | None: ...
    def record(
        self,
        company: UUID,
        actor: UUID,
        key: str,
        fingerprint: str,
        statement_set: UUID,
        now: datetime,
    ) -> None: ...
    def add_set(self, statement_set: StatementSet, generated_by: UUID) -> None: ...
    def add_statement(
        self,
        company: UUID,
        set_id: UUID,
        statement_id: UUID,
        kind: str,
        snapshot_id: UUID,
        snapshot_digest: str,
        source_digest: str,
        mapping_digest: str,
        now: datetime,
    ) -> None: ...
    def add_line(
        self,
        company: UUID,
        snapshot_id: UUID,
        line_id: UUID,
        report_line_id: UUID,
        amount: Decimal,
        source_digest: str,
    ) -> None: ...
    def add_source(
        self, company: UUID, line_id: UUID, account: UUID, journal_line: UUID, amount: Decimal
    ) -> None: ...


class ReportingUnitOfWork(ClosingUnitOfWork, Protocol):
    @property
    def statements(self) -> StatementStore: ...
