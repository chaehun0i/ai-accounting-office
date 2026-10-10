import builtins
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.contracts.access_errors import ResourceNotFound
from app.master_data.counterparties.domain.children import Address, BankReference, Contact, Role
from app.master_data.counterparties.domain.entities import Counterparty
from app.master_data.counterparties.infrastructure.models import (
    CounterpartyAddressModel,
    CounterpartyBankReferenceModel,
    CounterpartyContactModel,
    CounterpartyModel,
    CounterpartyRoleModel,
)


class CounterpartyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def entity(row: CounterpartyModel) -> Counterparty:
        return Counterparty(**{key: getattr(row, key) for key in Counterparty.__dataclass_fields__})

    def get(self, *, company_id: UUID, resource_id: UUID) -> Counterparty | None:
        row = self.session.scalar(
            select(CounterpartyModel).where(
                CounterpartyModel.company_id == company_id, CounterpartyModel.id == resource_id
            )
        )
        return self.entity(row) if row else None

    def by_code(self, *, company_id: UUID, code: str) -> Counterparty | None:
        row = self.session.scalar(
            select(CounterpartyModel).where(
                CounterpartyModel.company_id == company_id,
                CounterpartyModel.counterparty_code == code,
            )
        )
        return self.entity(row) if row else None

    def list(
        self,
        company_id: UUID,
        *,
        name: str | None = None,
        status: str | None = None,
        role: str | None = None,
    ) -> builtins.list[Counterparty]:
        query = select(CounterpartyModel).where(CounterpartyModel.company_id == company_id)
        if name:
            query = query.where(CounterpartyModel.display_name.contains(name, autoescape=True))
        if status:
            query = query.where(CounterpartyModel.status == status)
        if role:
            query = query.where(
                select(CounterpartyRoleModel.id)
                .where(
                    CounterpartyRoleModel.counterparty_id == CounterpartyModel.id,
                    CounterpartyRoleModel.role_code == role,
                    CounterpartyRoleModel.effective_from <= func.current_date(),
                    (CounterpartyRoleModel.effective_to.is_(None))
                    | (CounterpartyRoleModel.effective_to >= func.current_date()),
                )
                .exists()
            )
        return [
            self.entity(row)
            for row in self.session.scalars(
                query.order_by(CounterpartyModel.display_name, CounterpartyModel.id).limit(100)
            )
        ]

    def match(
        self, company_id: UUID, business_number: str | None, legal_name: str
    ) -> builtins.list[Counterparty]:
        query = select(CounterpartyModel).where(CounterpartyModel.company_id == company_id)
        if business_number:
            rows = list(
                self.session.scalars(
                    query.where(CounterpartyModel.business_number == business_number)
                )
            )
            if rows:
                return [self.entity(row) for row in rows]
        return [
            self.entity(row)
            for row in self.session.scalars(
                query.where(CounterpartyModel.normalized_legal_name == legal_name).order_by(
                    CounterpartyModel.id
                )
            )
        ]

    def add(self, value: Counterparty) -> None:
        self.session.add(CounterpartyModel(**asdict(value)))
        self.session.flush()

    def update(self, value: Counterparty, expected_version: int) -> bool:
        values = asdict(value)
        values.pop("id")
        values.pop("company_id")
        return (
            self.session.scalar(
                update(CounterpartyModel)
                .where(
                    CounterpartyModel.company_id == value.company_id,
                    CounterpartyModel.id == value.id,
                    CounterpartyModel.version == expected_version,
                )
                .values(**values)
                .returning(CounterpartyModel.id)
            )
            is not None
        )

    def _require(self, company_id: UUID, resource_id: UUID) -> None:
        if self.get(company_id=company_id, resource_id=resource_id) is None:
            raise ResourceNotFound()

    def add_role(self, company_id: UUID, value: Role) -> None:
        self._require(company_id, value.counterparty_id)
        self.session.add(CounterpartyRoleModel(**asdict(value)))
        self.session.flush()

    def add_contact(self, company_id: UUID, value: Contact) -> None:
        self._require(company_id, value.counterparty_id)
        self.session.add(CounterpartyContactModel(**asdict(value)))
        self.session.flush()

    def add_address(self, company_id: UUID, value: Address) -> None:
        self._require(company_id, value.counterparty_id)
        self.session.add(CounterpartyAddressModel(**asdict(value)))
        self.session.flush()

    def add_bank(self, company_id: UUID, value: BankReference) -> None:
        self._require(company_id, value.counterparty_id)
        self.session.add(CounterpartyBankReferenceModel(**asdict(value)))
        self.session.flush()

    def roles(self, company_id: UUID, resource_id: UUID) -> builtins.list[Role]:
        self._require(company_id, resource_id)
        return [
            Role(**{k: getattr(row, k) for k in Role.__dataclass_fields__})
            for row in self.session.scalars(
                select(CounterpartyRoleModel)
                .where(CounterpartyRoleModel.counterparty_id == resource_id)
                .order_by(CounterpartyRoleModel.effective_from, CounterpartyRoleModel.id)
            )
        ]

    def contacts(self, company_id: UUID, resource_id: UUID) -> builtins.list[Contact]:
        self._require(company_id, resource_id)
        return [
            Contact(**{k: getattr(row, k) for k in Contact.__dataclass_fields__})
            for row in self.session.scalars(
                select(CounterpartyContactModel).where(
                    CounterpartyContactModel.counterparty_id == resource_id
                )
            )
        ]

    def addresses(self, company_id: UUID, resource_id: UUID) -> builtins.list[Address]:
        self._require(company_id, resource_id)
        return [
            Address(**{k: getattr(row, k) for k in Address.__dataclass_fields__})
            for row in self.session.scalars(
                select(CounterpartyAddressModel).where(
                    CounterpartyAddressModel.counterparty_id == resource_id
                )
            )
        ]

    def banks(self, company_id: UUID, resource_id: UUID) -> builtins.list[BankReference]:
        self._require(company_id, resource_id)
        return [
            BankReference(**{k: getattr(row, k) for k in BankReference.__dataclass_fields__})
            for row in self.session.scalars(
                select(CounterpartyBankReferenceModel).where(
                    CounterpartyBankReferenceModel.counterparty_id == resource_id
                )
            )
        ]
