from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting.accounts.domain.entities import Account
from app.accounting.accounts.infrastructure.models import AccountModel


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def entity(row: AccountModel) -> Account:
        return Account(**{k: getattr(row, k) for k in Account.__dataclass_fields__})

    def get(self, *, company_id: UUID, resource_id: UUID) -> Account | None:
        row = self.session.scalar(
            select(AccountModel).where(
                AccountModel.company_id == company_id, AccountModel.id == resource_id
            )
        )
        return self.entity(row) if row else None

    def list(self, company_id: UUID) -> list[Account]:
        return [
            self.entity(row)
            for row in self.session.scalars(
                select(AccountModel)
                .where(AccountModel.company_id == company_id)
                .order_by(AccountModel.account_code)
            )
        ]

    def add(self, value: Account) -> None:
        self.session.add(AccountModel(**asdict(value)))
        self.session.flush()
