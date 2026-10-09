from collections.abc import Callable
from dataclasses import replace
from datetime import date
from uuid import UUID

from app.accounting.application.contracts import MasterUnitOfWork
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, VersionConflict
from app.identity.users.domain.entities import Principal
from app.master_data.counterparties.domain.children import Address, BankReference, Contact, Role
from app.master_data.counterparties.domain.entities import Counterparty
from app.master_data.domain.rules import (
    CounterpartyRole,
    CounterpartyType,
    DueRule,
    MasterStatus,
    due_date,
    normalized_identifier,
    normalized_name,
    validate_currency,
)
from app.master_data.payment_terms.domain.entities import PaymentTerm


class MasterDataService:
    def __init__(self, factory: Callable[[], MasterUnitOfWork]) -> None:
        self.factory = factory

    def payment_terms(self, principal: Principal, company_id: UUID) -> list[PaymentTerm]:
        with self.factory() as uow:
            require_company(uow, principal, company_id, "counterparty.read")
            return uow.payment_terms.list(company_id)

    def create_payment_term(self, principal: Principal, value: PaymentTerm) -> PaymentTerm:
        try:
            rule = DueRule(value.due_rule_type)
        except ValueError:
            raise InvalidInput() from None
        due_date(date(2026, 1, 1), rule, value.due_days)
        with self.factory() as uow:
            require_company(uow, principal, value.company_id, "counterparty.create")
            value = replace(value, created_at=uow.now(), updated_at=uow.now())
            uow.payment_terms.add(value)
            return value

    def list_counterparties(
        self,
        principal: Principal,
        company_id: UUID,
        *,
        name: str | None = None,
        status: str | None = None,
        role: str | None = None,
    ) -> list[Counterparty]:
        with self.factory() as uow:
            require_company(uow, principal, company_id, "counterparty.read")
            return uow.counterparties.list(company_id, name=name, status=status, role=role)

    def get_counterparty(
        self, principal: Principal, company_id: UUID, resource_id: UUID
    ) -> tuple[Counterparty, list[Role], list[Contact], list[Address], list[BankReference]]:
        with self.factory() as uow:
            require_company(uow, principal, company_id, "counterparty.read")
            value = uow.counterparties.get(company_id=company_id, resource_id=resource_id)
            if value is None:
                raise ResourceNotFound()
            return (
                value,
                uow.counterparties.roles(company_id, resource_id),
                uow.counterparties.contacts(company_id, resource_id),
                uow.counterparties.addresses(company_id, resource_id),
                uow.counterparties.banks(company_id, resource_id),
            )

    def create_counterparty(
        self,
        principal: Principal,
        value: Counterparty,
        *,
        roles: tuple[Role, ...] = (),
        contacts: tuple[Contact, ...] = (),
        addresses: tuple[Address, ...] = (),
        bank_refs: tuple[BankReference, ...] = (),
    ) -> Counterparty:
        validate_currency(value.default_currency_code)
        if value.counterparty_type not in CounterpartyType or value.status not in MasterStatus:
            raise InvalidInput()
        if not normalized_name(value.legal_name) or not value.display_name.strip():
            raise InvalidInput()
        value = replace(
            value,
            business_number=normalized_identifier(value.business_number, 10),
            corporation_number=normalized_identifier(value.corporation_number, 13),
            normalized_legal_name=normalized_name(value.legal_name),
        )
        with self.factory() as uow:
            require_company(uow, principal, value.company_id, "counterparty.create")
            self._payment_term(uow, value.company_id, value.payment_term_id)
            value = replace(value, created_at=uow.now(), updated_at=uow.now())
            uow.counterparties.add(value)
            for role in roles:
                self._role(role)
                uow.counterparties.add_role(
                    value.company_id, replace(role, counterparty_id=value.id)
                )
            for contact in contacts:
                uow.counterparties.add_contact(
                    value.company_id, replace(contact, counterparty_id=value.id)
                )
            for address in addresses:
                uow.counterparties.add_address(
                    value.company_id, replace(address, counterparty_id=value.id)
                )
            for bank in bank_refs:
                uow.counterparties.add_bank(
                    value.company_id, replace(bank, counterparty_id=value.id)
                )
            return value

    def update_counterparty(
        self,
        principal: Principal,
        company_id: UUID,
        resource_id: UUID,
        expected_version: int,
        *,
        display_name: str | None = None,
        legal_name: str | None = None,
        payment_term_id: UUID | None = None,
        clear_payment_term: bool = False,
        status: str | None = None,
    ) -> Counterparty:
        with self.factory() as uow:
            require_company(uow, principal, company_id, "counterparty.update")
            current = uow.counterparties.get(company_id=company_id, resource_id=resource_id)
            if current is None:
                raise ResourceNotFound()
            if current.version != expected_version:
                raise VersionConflict()
            term = None if clear_payment_term else payment_term_id or current.payment_term_id
            self._payment_term(uow, company_id, term)
            if status is not None and status not in MasterStatus:
                raise InvalidInput()
            value = replace(
                current,
                display_name=display_name or current.display_name,
                legal_name=legal_name or current.legal_name,
                normalized_legal_name=normalized_name(legal_name or current.legal_name),
                payment_term_id=term,
                status=status or current.status,
                version=current.version + 1,
                updated_at=uow.now(),
            )
            if not uow.counterparties.update(value, expected_version):
                raise VersionConflict()
            return value

    def add_role(
        self, principal: Principal, company_id: UUID, value: Role, expected_version: int
    ) -> Role:
        self._role(value)
        with self.factory() as uow:
            require_company(uow, principal, company_id, "counterparty.update")
            current = uow.counterparties.get(
                company_id=company_id, resource_id=value.counterparty_id
            )
            if current is None:
                raise ResourceNotFound()
            if current.version != expected_version:
                raise VersionConflict()
            uow.counterparties.add_role(company_id, value)
            updated = replace(current, version=current.version + 1, updated_at=uow.now())
            if not uow.counterparties.update(updated, expected_version):
                raise VersionConflict()
            return value

    @staticmethod
    def _role(value: Role) -> None:
        if value.role_code not in CounterpartyRole or (
            value.effective_to is not None and value.effective_to < value.effective_from
        ):
            raise InvalidInput()

    @staticmethod
    def _payment_term(uow: MasterUnitOfWork, company_id: UUID, resource_id: UUID | None) -> None:
        if resource_id is not None:
            term = uow.payment_terms.get(company_id=company_id, resource_id=resource_id)
            if term is None:
                raise ResourceNotFound()
            if not term.is_active:
                raise InvalidInput()
