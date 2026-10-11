from typing import Self

from app.accounting.transactions.infrastructure.unit_of_work import TransactionSQLAlchemyUnitOfWork
from app.intake.infrastructure.repository import ImportRepository
from app.intake.promotion.infrastructure.repository import PromotionRepository


class PromotionSQLAlchemyUnitOfWork(TransactionSQLAlchemyUnitOfWork):
    imports: ImportRepository
    promotions: PromotionRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.imports = ImportRepository(self.session)
        self.promotions = PromotionRepository(self.session)
        return self
