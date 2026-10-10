from collections.abc import Callable
from datetime import date
from typing import Protocol
from uuid import UUID

from app.accounting.journals.application.contracts import JournalUnitOfWork
from app.accounting.ledger.domain.entities import (
    LedgerFact,
    LedgerRow,
    TrialRow,
    ledger,
    trial_balance,
)
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound
from app.identity.users.domain.entities import Principal


class LedgerReader(Protocol):
    def facts(
        self, company: UUID, date_to: date, account_id: UUID | None = None
    ) -> list[LedgerFact]: ...


class ReportUnitOfWork(JournalUnitOfWork, Protocol):
    @property
    def ledger(self) -> LedgerReader: ...


class AccountingReports:
    def __init__(self, factory: Callable[[], ReportUnitOfWork]) -> None:
        self.factory = factory

    def ledger(
        self, actor: Principal, company: UUID, account: UUID, date_from: date, date_to: date
    ) -> list[LedgerRow]:
        if date_from > date_to:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "ledger.read")
            if uow.accounts.get(company_id=company, resource_id=account) is None:
                raise ResourceNotFound()
            return ledger(uow.ledger.facts(company, date_to, account), date_from)

    def trial(self, actor: Principal, company: UUID, period_id: UUID) -> list[TrialRow]:
        with self.factory() as uow:
            require_company(uow, actor, company, "trial_balance.read")
            period = uow.periods.get(company_id=company, resource_id=period_id)
            if period is None:
                raise ResourceNotFound()
            return trial_balance(uow.ledger.facts(company, period.end_date), period.start_date)
