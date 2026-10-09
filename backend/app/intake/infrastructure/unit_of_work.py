from typing import Self

from app.companies.infrastructure.unit_of_work import CompanySQLAlchemyUnitOfWork
from app.intake.infrastructure.repository import ImportRepository


class IntakeSQLAlchemyUnitOfWork(CompanySQLAlchemyUnitOfWork):
    imports: ImportRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.imports = ImportRepository(self.session)
        return self
