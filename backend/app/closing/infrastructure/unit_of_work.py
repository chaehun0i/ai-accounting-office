from typing import Self

from app.closing.infrastructure.repository import ClosingRepository
from app.finance.banking.infrastructure.unit_of_work import BankingSQLAlchemyUnitOfWork


class ClosingSQLAlchemyUnitOfWork(BankingSQLAlchemyUnitOfWork):
    closing: ClosingRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.closing = ClosingRepository(self.session)
        return self
