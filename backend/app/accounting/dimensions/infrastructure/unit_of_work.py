from typing import Self

from app.accounting.dimensions.infrastructure.repository import DimensionRepository
from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork


class DimensionSQLAlchemyUnitOfWork(MasterSQLAlchemyUnitOfWork):
    dimensions: DimensionRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.dimensions = DimensionRepository(self.session)
        return self
