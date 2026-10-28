from typing import Self

from app.accounting.transactions.infrastructure.unit_of_work import TransactionSQLAlchemyUnitOfWork
from app.tax.repository import TaxRepository


class TaxUnitOfWork(TransactionSQLAlchemyUnitOfWork):
    tax: TaxRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.tax = TaxRepository(self.session)
        return self
