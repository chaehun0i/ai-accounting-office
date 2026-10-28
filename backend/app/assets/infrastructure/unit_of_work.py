from typing import Self

from app.accounting.journals.infrastructure.unit_of_work import JournalSQLAlchemyUnitOfWork
from app.assets.infrastructure.repository import AssetRepository


class AssetSQLAlchemyUnitOfWork(JournalSQLAlchemyUnitOfWork):
    assets: AssetRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.assets = AssetRepository(self.session)
        return self
