from typing import Self

from app.reporting.cash_flow.repository import CashFlowRepository
from app.reporting.financial_statements.infrastructure.unit_of_work import (
    ReportingSQLAlchemyUnitOfWork,
)


class CashFlowUnitOfWork(ReportingSQLAlchemyUnitOfWork):
    cash_flow: CashFlowRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.cash_flow = CashFlowRepository(self.session)
        return self
