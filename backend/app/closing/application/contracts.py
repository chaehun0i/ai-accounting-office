"""결산 Application이 필요로 하는 회사 범위 저장소와 작업단위 계약입니다."""

from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.closing.domain.entities import (
    ClosingAdjustment,
    ClosingApproval,
    ClosingCheckResult,
    ClosingRun,
)
from app.finance.banking.application.contracts import BankingUnitOfWork


class ClosingStore(Protocol):
    def run(self, company: UUID, identifier: UUID, *, lock: bool = False) -> ClosingRun | None: ...
    def runs(self, company: UUID, period: UUID) -> list[ClosingRun]: ...
    def add_run(self, value: ClosingRun) -> None: ...
    def update_run(self, value: ClosingRun) -> None: ...
    def checks(self, company: UUID, run: UUID) -> tuple[ClosingCheckResult, ...]: ...
    def replace_checks(
        self, company: UUID, run: UUID, checks: tuple[ClosingCheckResult, ...], now: datetime
    ) -> None: ...
    def adjustments(self, company: UUID, run: UUID) -> list[ClosingAdjustment]: ...
    def adjustment(
        self, company: UUID, identifier: UUID, *, lock: bool = False
    ) -> ClosingAdjustment | None: ...
    def add_adjustment(
        self,
        value: ClosingAdjustment,
        now: datetime,
        source_type: str | None,
        source_id: UUID | None,
    ) -> None: ...
    def update_adjustment(self, value: ClosingAdjustment, expected_version: int) -> None: ...
    def approval(
        self, company: UUID, identifier: UUID, *, lock: bool = False
    ) -> ClosingApproval | None: ...
    def approvals(self, company: UUID, run: UUID) -> list[ClosingApproval]: ...
    def add_approval(self, value: ClosingApproval) -> None: ...
    def update_approval(self, value: ClosingApproval) -> None: ...
    def pending(self, company: UUID, start: date, end: date) -> tuple[int, int]: ...
    def cutoff_count(self, company: UUID, start: date, end: date) -> int: ...
    def replay(
        self, company: UUID, actor: UUID, code: str, key: str, fingerprint: str
    ) -> tuple[UUID, UUID | None, UUID | None] | None: ...
    def record(
        self,
        company: UUID,
        actor: UUID,
        code: str,
        key: str,
        fingerprint: str,
        run: UUID,
        now: datetime,
        adjustment: UUID | None = None,
        approval: UUID | None = None,
        before: str = "",
        after: str = "",
    ) -> None: ...


class ClosingUnitOfWork(BankingUnitOfWork, Protocol):
    @property
    def closing(self) -> ClosingStore: ...
