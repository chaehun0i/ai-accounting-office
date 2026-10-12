from typing import Self

from app.finance.banking.infrastructure.repository import BankingRepository
from app.finance.settlements.infrastructure.unit_of_work import FinanceSQLAlchemyUnitOfWork
from app.intake.infrastructure.repository import ImportRepository


class BankingSQLAlchemyUnitOfWork(FinanceSQLAlchemyUnitOfWork):
    banking: BankingRepository
    imports: ImportRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.banking = BankingRepository(self.session)
        self.imports = ImportRepository(self.session)
        return self
