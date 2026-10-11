from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.accounting.transactions.application.contracts import TransactionUnitOfWork
from app.intake.application.contracts import IntakeUnitOfWork
from app.intake.domain.entities import Import, PromotionRow, Receipt


class Promotions(Protocol):
    def lock_request(self, company: UUID, actor: UUID, key: str) -> None: ...
    def replay(self, company: UUID, actor: UUID, key: str, fingerprint: str) -> UUID | None: ...
    def evidence(self, value: Import) -> UUID: ...
    def finish(
        self, value: Import, receipt: Receipt, rows: list[PromotionRow], now: datetime
    ) -> None: ...
    def record(
        self,
        value: Import,
        receipt: Receipt,
        actor: UUID,
        key: str,
        fingerprint: str,
        now: datetime,
    ) -> None: ...


class PromotionUnitOfWork(TransactionUnitOfWork, IntakeUnitOfWork, Protocol):
    @property
    def promotions(self) -> Promotions: ...
