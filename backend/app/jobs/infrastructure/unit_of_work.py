from typing import Self

from app.companies.infrastructure.unit_of_work import CompanySQLAlchemyUnitOfWork
from app.jobs.infrastructure.repository import RuntimeRepository


class RuntimeSQLAlchemyUnitOfWork(CompanySQLAlchemyUnitOfWork):
    runtime: RuntimeRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.runtime = RuntimeRepository(self.session)
        return self
