from typing import Self

from app.closing.infrastructure.unit_of_work import ClosingSQLAlchemyUnitOfWork
from app.reporting.financial_statements.infrastructure.repository import StatementRepository


class ReportingSQLAlchemyUnitOfWork(ClosingSQLAlchemyUnitOfWork):
    statements: StatementRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.statements = StatementRepository(self.session)
        return self
