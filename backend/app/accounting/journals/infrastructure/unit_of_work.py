from typing import Self
from uuid import UUID

from sqlalchemy import select

from app.accounting.accounts.infrastructure.models import AccountModel
from app.accounting.journals.infrastructure.repository import JournalRepository
from app.accounting.periods.infrastructure.models import PeriodModel
from app.accounting.transactions.infrastructure.unit_of_work import TransactionSQLAlchemyUnitOfWork


class JournalSQLAlchemyUnitOfWork(TransactionSQLAlchemyUnitOfWork):
    journals: JournalRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.journals = JournalRepository(self.session)
        return self

    def lock_period(self, company_id: UUID, period_id: UUID) -> None:
        self.session.scalar(
            select(PeriodModel)
            .where(PeriodModel.company_id == company_id, PeriodModel.id == period_id)
            .with_for_update()
        )

    def lock_accounts(self, company_id: UUID, account_ids: tuple[UUID, ...]) -> None:
        list(
            self.session.scalars(
                select(AccountModel)
                .where(AccountModel.company_id == company_id, AccountModel.id.in_(account_ids))
                .order_by(AccountModel.id)
                .with_for_update()
            )
        )
