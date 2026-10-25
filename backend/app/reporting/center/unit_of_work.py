from typing import Self

from app.reporting.center.repository import ReportRunRepository
from app.reporting.financial_statements.infrastructure.unit_of_work import (
    ReportingSQLAlchemyUnitOfWork,
)


class ReportCenterUnitOfWork(ReportingSQLAlchemyUnitOfWork):
    report_runs: ReportRunRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.report_runs = ReportRunRepository(self.session)
        return self
