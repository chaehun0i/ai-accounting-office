from typing import Self
from app.onboarding.infrastructure.repository import OnboardingRepository
from app.accounting.opening_balances.infrastructure.repository import OpeningRepository

from app.accounting.journals.infrastructure.unit_of_work import JournalSQLAlchemyUnitOfWork
from app.accounting.ledger.infrastructure.repository import LedgerRepository
from app.approvals.infrastructure.repository import GovernanceRepository


class AccountingSQLAlchemyUnitOfWork(JournalSQLAlchemyUnitOfWork):
    governance: GovernanceRepository
    ledger: LedgerRepository
    onboarding: OnboardingRepository
    openings: OpeningRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.governance = GovernanceRepository(self.session)
        self.ledger = LedgerRepository(self.session)
        self.onboarding = OnboardingRepository(self.session)
        self.openings = OpeningRepository(self.session)
        return self
