from typing import Self

from app.companies.infrastructure.repository import CompanyRepository
from app.identity.infrastructure.unit_of_work import IdentitySQLAlchemyUnitOfWork


class CompanySQLAlchemyUnitOfWork(IdentitySQLAlchemyUnitOfWork):
    companies: CompanyRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.companies = CompanyRepository(self.session)
        return self
