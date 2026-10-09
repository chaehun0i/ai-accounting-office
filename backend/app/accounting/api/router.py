from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from app.accounting.api.schemas import (
    AccountRead,
    AddressRead,
    BankReferenceRead,
    ContactRead,
    CounterpartyCreate,
    CounterpartyDetail,
    CounterpartyFilter,
    CounterpartyRead,
    CounterpartyStatusCommand,
    CounterpartyUpdate,
    InitializeAccountingMaster,
    PaymentTermCreate,
    PaymentTermRead,
    PeriodRead,
    RoleCreate,
    RoleRead,
    SettingsRead,
    SettingsUpdate,
    TemplateRead,
)
from app.accounting.application.service import AccountingMasterService
from app.composition import Services
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf, principal, services
from app.identity.users.domain.entities import Principal
from app.master_data.application.service import MasterDataService
from app.master_data.counterparties.domain.children import Address, BankReference, Contact, Role
from app.master_data.counterparties.domain.entities import Counterparty
from app.master_data.payment_terms.domain.entities import PaymentTerm

router = APIRouter(tags=["회계 마스터"])
Actor = Annotated[Principal, Depends(principal)]
Container = Annotated[Services, Depends(services)]
CompanyScope = Annotated[UUID, Header(alias="X-Company-ID")]


def accounting(container: Container) -> AccountingMasterService:
    if container.accounting is None:
        raise DatabaseUnavailable()
    return container.accounting


def master_data(container: Container) -> MasterDataService:
    if container.master_data is None:
        raise DatabaseUnavailable()
    return container.master_data


Accounting = Annotated[AccountingMasterService, Depends(accounting)]
MasterData = Annotated[MasterDataService, Depends(master_data)]


def counterparty_read(value: Counterparty) -> CounterpartyRead:
    data = asdict(value)
    # 조회 응답에서는 식별자의 마지막 세 자리만 표시합니다.
    for key in ("business_number", "corporation_number"):
        identifier = data[key]
        if identifier:
            data[key] = "*" * (len(identifier) - 3) + identifier[-3:]
    return CounterpartyRead.model_validate(data)


@router.get("/accounting/settings", response_model=SettingsRead)
def read_settings(actor: Actor, company_id: CompanyScope, service: Accounting) -> SettingsRead:
    return SettingsRead.model_validate(asdict(service.settings(actor, company_id)))


@router.patch("/accounting/settings", response_model=SettingsRead, dependencies=[Depends(csrf)])
def update_settings(
    payload: SettingsUpdate, actor: Actor, company_id: CompanyScope, service: Accounting
) -> SettingsRead:
    return SettingsRead.model_validate(
        asdict(service.update_settings(actor, company_id, **payload.model_dump()))
    )


@router.post("/accounting/initialize", response_model=SettingsRead, dependencies=[Depends(csrf)])
def initialize(
    payload: InitializeAccountingMaster, actor: Actor, company_id: CompanyScope, service: Accounting
) -> SettingsRead:
    return SettingsRead.model_validate(
        asdict(service.initialize(actor, company_id, **payload.model_dump()))
    )


@router.get("/accounts", response_model=list[AccountRead])
def accounts(actor: Actor, company_id: CompanyScope, service: Accounting) -> list[AccountRead]:
    return [AccountRead.model_validate(asdict(row)) for row in service.accounts(actor, company_id)]


@router.get("/account-templates", response_model=list[TemplateRead])
def templates(actor: Actor, company_id: CompanyScope, service: Accounting) -> list[TemplateRead]:
    return [
        TemplateRead.model_validate(asdict(row)) for row in service.templates(actor, company_id)
    ]


@router.get("/accounting/periods", response_model=list[PeriodRead])
def periods(actor: Actor, company_id: CompanyScope, service: Accounting) -> list[PeriodRead]:
    return [PeriodRead.model_validate(asdict(row)) for row in service.periods(actor, company_id)]


@router.get("/payment-terms", response_model=list[PaymentTermRead])
def payment_terms(
    actor: Actor, company_id: CompanyScope, service: MasterData
) -> list[PaymentTermRead]:
    return [
        PaymentTermRead.model_validate(asdict(row))
        for row in service.payment_terms(actor, company_id)
    ]


@router.post(
    "/payment-terms", response_model=PaymentTermRead, status_code=201, dependencies=[Depends(csrf)]
)
def create_payment_term(
    payload: PaymentTermCreate, actor: Actor, company_id: CompanyScope, service: MasterData
) -> PaymentTermRead:
    value = PaymentTerm(company_id=company_id, **payload.model_dump())
    return PaymentTermRead.model_validate(asdict(service.create_payment_term(actor, value)))


@router.get("/counterparties", response_model=list[CounterpartyRead])
def counterparties(
    filters: Annotated[CounterpartyFilter, Query()],
    actor: Actor,
    company_id: CompanyScope,
    service: MasterData,
) -> list[CounterpartyRead]:
    return [
        counterparty_read(row)
        for row in service.list_counterparties(actor, company_id, **filters.model_dump())
    ]


@router.post(
    "/counterparties",
    response_model=CounterpartyRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def create_counterparty(
    payload: CounterpartyCreate, actor: Actor, company_id: CompanyScope, service: MasterData
) -> CounterpartyRead:
    value = Counterparty(
        company_id=company_id,
        normalized_legal_name="",
        **payload.model_dump(exclude={"roles", "contacts", "addresses", "bank_refs"}),
    )
    return counterparty_read(
        service.create_counterparty(
            actor,
            value,
            roles=tuple(
                Role(counterparty_id=value.id, **row.model_dump()) for row in payload.roles
            ),
            contacts=tuple(
                Contact(counterparty_id=value.id, **row.model_dump()) for row in payload.contacts
            ),
            addresses=tuple(
                Address(counterparty_id=value.id, **row.model_dump()) for row in payload.addresses
            ),
            bank_refs=tuple(
                BankReference(counterparty_id=value.id, **row.model_dump())
                for row in payload.bank_refs
            ),
        )
    )


@router.get("/counterparties/{resource_id}", response_model=CounterpartyDetail)
def counterparty(
    resource_id: UUID, actor: Actor, company_id: CompanyScope, service: MasterData
) -> CounterpartyDetail:
    value, roles, contacts, addresses, banks = service.get_counterparty(
        actor, company_id, resource_id
    )
    return CounterpartyDetail(
        **counterparty_read(value).model_dump(),
        roles=[RoleRead.model_validate(asdict(row)) for row in roles],
        contacts=[ContactRead.model_validate(asdict(row)) for row in contacts],
        addresses=[AddressRead.model_validate(asdict(row)) for row in addresses],
        bank_refs=[BankReferenceRead.model_validate(asdict(row)) for row in banks],
    )


@router.patch(
    "/counterparties/{resource_id}", response_model=CounterpartyRead, dependencies=[Depends(csrf)]
)
def update_counterparty(
    resource_id: UUID,
    payload: CounterpartyUpdate,
    actor: Actor,
    company_id: CompanyScope,
    service: MasterData,
) -> CounterpartyRead:
    return counterparty_read(
        service.update_counterparty(actor, company_id, resource_id, **payload.model_dump())
    )


@router.post(
    "/counterparties/{resource_id}/status",
    response_model=CounterpartyRead,
    dependencies=[Depends(csrf)],
)
def change_counterparty_status(
    resource_id: UUID,
    payload: CounterpartyStatusCommand,
    actor: Actor,
    company_id: CompanyScope,
    service: MasterData,
) -> CounterpartyRead:
    return counterparty_read(
        service.update_counterparty(actor, company_id, resource_id, **payload.model_dump())
    )


@router.post(
    "/counterparties/{resource_id}/roles",
    response_model=RoleRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def add_role(
    resource_id: UUID,
    payload: RoleCreate,
    actor: Actor,
    company_id: CompanyScope,
    service: MasterData,
) -> RoleRead:
    return RoleRead.model_validate(
        asdict(
            service.add_role(
                actor, company_id, Role(counterparty_id=resource_id, **payload.model_dump())
            )
        )
    )
