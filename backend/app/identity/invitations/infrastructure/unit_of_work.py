from typing import Self

from app.companies.infrastructure.unit_of_work import CompanySQLAlchemyUnitOfWork
from app.identity.invitations.infrastructure.repository import InvitationRepository


class InvitationSQLAlchemyUnitOfWork(CompanySQLAlchemyUnitOfWork):
    invitations: InvitationRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.invitations = InvitationRepository(self.session)
        return self
