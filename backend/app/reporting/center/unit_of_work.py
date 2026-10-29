from typing import Self

from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.center.repository import ReportRunRepository


class ReportCenterUnitOfWork(CashFlowUnitOfWork):
    report_runs: ReportRunRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.report_runs = ReportRunRepository(self.session)
        return self
