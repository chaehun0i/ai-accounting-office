from typing import Self
from uuid import UUID

from sqlalchemy import select

from app.accounting.periods.infrastructure.models import PeriodModel
from app.closing.infrastructure.repository import ClosingRepository
from app.finance.banking.infrastructure.unit_of_work import BankingSQLAlchemyUnitOfWork


class ClosingSQLAlchemyUnitOfWork(BankingSQLAlchemyUnitOfWork):
    closing: ClosingRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.closing = ClosingRepository(self.session)
        return self

    def lock_period(self, company_id: UUID, period_id: UUID) -> None:
        self.session.scalar(
            select(PeriodModel)
            .where(PeriodModel.company_id == company_id, PeriodModel.id == period_id)
            .with_for_update()
        )
