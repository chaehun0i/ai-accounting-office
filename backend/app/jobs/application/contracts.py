from datetime import datetime
from decimal import Decimal
from typing import Protocol, Self
from uuid import UUID

from app.companies.application.contracts import CompanyUnitOfWork
from app.identity.users.domain.entities import Principal
from app.jobs.domain.runtime import EventRead, RunRead, StepRead


class RuntimeRecords(Protocol):
    def create(
        self,
        actor: Principal,
        company: UUID,
        transaction: UUID | None,
        provider: str,
        model: str,
        key: str,
        fingerprint: str,
        now: datetime,
        period_id: UUID | None = None,
        question_text: str | None = None,
        graph_name: str = "bookkeeper",
    ) -> RunRead: ...
    def get(self, company: UUID, run: UUID, *, lock: bool = False) -> RunRead | None: ...
    def claim(self, company: UUID, run: UUID, worker: UUID, now: datetime) -> bool: ...
    def tool_started(self, company: UUID, run: UUID, code: str, now: datetime) -> None: ...
    def finish(
        self,
        company: UUID,
        run: UUID,
        status: str,
        stage: str,
        now: datetime,
        verdict: str | None = None,
        journal: UUID | None = None,
        error: str | None = None,
        answer_text: str | None = None,
        answer_amount: Decimal | None = None,
        answer_resource_id: UUID | None = None,
        answer_source_digest: str | None = None,
    ) -> None: ...
    def begin_step(self, company: UUID, run: UUID, node: str, now: datetime) -> UUID: ...
    def finish_step(
        self,
        company: UUID,
        run: UUID,
        step: UUID,
        status: str,
        now: datetime,
        error: str | None = None,
    ) -> None: ...
    def tool(
        self,
        company: UUID,
        run: UUID,
        step: UUID | None,
        code: str,
        input_digest: str,
        output_digest: str,
        status: str,
        latency: int,
        error: str | None,
        now: datetime,
    ) -> None: ...
    def steps(self, company: UUID, run: UUID) -> list[StepRead]: ...
    def events(self, company: UUID, run: UUID, after: int) -> list[EventRead]: ...


class RuntimeUnitOfWork(CompanyUnitOfWork, Protocol):
    @property
    def runtime(self) -> RuntimeRecords: ...
    def __enter__(self) -> Self: ...
