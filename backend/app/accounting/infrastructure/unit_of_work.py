from typing import Self

from app.accounting.accounts.infrastructure.repository import AccountRepository
from app.accounting.periods.infrastructure.repository import PeriodRepository
from app.accounting.sequences.infrastructure.repository import SequenceRepository
from app.accounting.settings.infrastructure.repository import AccountingSettingsRepository
from app.accounting.templates.infrastructure.repository import TemplateRepository
from app.companies.infrastructure.unit_of_work import CompanySQLAlchemyUnitOfWork
from app.master_data.counterparties.infrastructure.repository import CounterpartyRepository
from app.master_data.payment_terms.infrastructure.repository import PaymentTermRepository


class MasterSQLAlchemyUnitOfWork(CompanySQLAlchemyUnitOfWork):
    payment_terms: PaymentTermRepository
    counterparties: CounterpartyRepository
    settings: AccountingSettingsRepository
    accounts: AccountRepository
    periods: PeriodRepository
    templates: TemplateRepository
    sequences: SequenceRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.payment_terms = PaymentTermRepository(self.session)
        self.counterparties = CounterpartyRepository(self.session)
        self.settings = AccountingSettingsRepository(self.session)
        self.accounts = AccountRepository(self.session)
        self.periods = PeriodRepository(self.session)
        self.templates = TemplateRepository(self.session)
        self.sequences = SequenceRepository(self.session)
        return self
