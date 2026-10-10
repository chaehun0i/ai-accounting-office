from typing import Self

from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.intake.infrastructure.repository import ImportRepository
from app.onboarding.infrastructure.repository import OnboardingRepository


class OnboardingSQLAlchemyUnitOfWork(MasterSQLAlchemyUnitOfWork):
    onboarding: OnboardingRepository
    imports: ImportRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.onboarding = OnboardingRepository(self.session)
        self.imports = ImportRepository(self.session)
        return self
