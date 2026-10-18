from dataclasses import asdict
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.accounting.accounts.domain.entities import Account
from app.accounting.accounts.infrastructure.models import AccountChangeModel, AccountModel


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def entity(row: AccountModel) -> Account:
        return Account(**{k: getattr(row, k) for k in Account.__dataclass_fields__})

    def get(self, *, company_id: UUID, resource_id: UUID, lock: bool = False) -> Account | None:
        query = select(AccountModel).where(
            AccountModel.company_id == company_id, AccountModel.id == resource_id
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
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

    def referenced(self, company: UUID, identifier: UUID) -> bool:
        # Every account FK is company scoped. A code change on a used account would
        # rewrite the historical GL/TB label even though journal lines retain the ID.
        sources = (
            ("journal_lines", "account_id"),
            ("opening_balance_lines", "account_id"),
            ("receivables", "account_id"),
            ("payables", "account_id"),
            ("bank_accounts", "control_account_id"),
            ("card_accounts", "control_account_id"),
            ("report_account_mappings", "account_id"),
            ("financial_statement_sources", "account_id"),
            ("chart_of_accounts", "parent_account_id"),
        )
        for table, column in sources:
            found = self.session.scalar(
                text(
                    f"SELECT 1 FROM {table} WHERE company_id=:company "
                    f"AND {column}=:identifier LIMIT 1"
                ),
                {"company": company, "identifier": identifier},
            )
            if found:
                return True
        return False

    def update(
        self, value: Account, expected_version: int, actor: UUID, action: str, reason: str | None
    ) -> bool:
        row = self.session.scalar(
            select(AccountModel)
            .where(AccountModel.company_id == value.company_id, AccountModel.id == value.id)
            .with_for_update()
        )
        if row is None or row.version != expected_version:
            return False
        before = self.entity(row)
        row.account_code = value.account_code
        row.account_name = value.account_name
        row.status = value.status
        row.version = value.version
        row.updated_at = value.updated_at
        self.session.add(
            AccountChangeModel(
                id=uuid4(),
                company_id=value.company_id,
                account_id=value.id,
                actor_id=actor,
                action=action,
                reason=reason,
                before_code=before.account_code,
                after_code=value.account_code,
                before_name=before.account_name,
                after_name=value.account_name,
                before_status=before.status,
                after_status=value.status,
                previous_version=before.version,
                next_version=value.version,
                occurred_at=value.updated_at,
            )
        )
        self.session.flush()
        return True

    def map_control(self, company: UUID, identifier: UUID, role: str) -> Account | None:
        row = self.session.scalar(
            select(AccountModel)
            .where(AccountModel.company_id == company, AccountModel.id == identifier)
            .with_for_update()
        )
        if row is None:
            return None
        if row.control_account_type not in {None, role}:
            from app.contracts.access_errors import StateConflict

            raise StateConflict()
        row.control_account_type = role
        self.session.flush()
        return self.entity(row)
