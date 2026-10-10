from typing import Self

from app.accounting.journals.infrastructure.unit_of_work import JournalSQLAlchemyUnitOfWork
from app.approvals.infrastructure.repository import GovernanceRepository


class AccountingSQLAlchemyUnitOfWork(JournalSQLAlchemyUnitOfWork):
    governance: GovernanceRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.governance = GovernanceRepository(self.session)
        return self
