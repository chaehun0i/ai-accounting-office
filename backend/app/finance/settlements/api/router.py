"""회사가 확인된 Application Service만 호출하는 재무 API입니다."""

from dataclasses import asdict
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.access_errors import ResourceNotFound
from app.contracts.errors import DatabaseUnavailable
from app.finance.reconciliation.application.service import FinanceReports
from app.finance.settlements.api.schemas import (
    AgingRead,
    Allocate,
    Confirm,
    ObligationRead,
    Recognize,
    ReconciliationRead,
    SettlementCreate,
    SettlementRead,
)
from app.finance.settlements.application.service import FinanceService
from app.finance.settlements.domain.entities import Allocation
from app.identity.auth.api.dependencies import csrf

router = APIRouter(tags=["채권·채무"])
Key = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$"),
]


def service(container: Container) -> FinanceService:
    if container.finance is None:
        raise DatabaseUnavailable()
    return container.finance


def reports(container: Container) -> FinanceReports:
    if container.finance_reports is None:
        raise DatabaseUnavailable()
    return container.finance_reports


Service = Annotated[FinanceService, Depends(service)]
Reports = Annotated[FinanceReports, Depends(reports)]


@router.get("/receivables", response_model=list[ObligationRead])
def list_receivables(
    as_of: date, actor: Actor, company_id: CompanyScope, service: Service
) -> list[ObligationRead]:
    return [
        ObligationRead.model_validate(asdict(value))
        for value in service.list(actor, company_id, "AR", as_of)
    ]


@router.get("/receivables/aging", response_model=AgingRead)
def aging_receivables(
    as_of: date, actor: Actor, company_id: CompanyScope, reports: Reports
) -> AgingRead:
    return AgingRead.model_validate(asdict(reports.aging(actor, company_id, "AR", as_of)))


@router.get("/receivables/reconciliation", response_model=ReconciliationRead)
def reconcile_receivables(
    as_of: date, actor: Actor, company_id: CompanyScope, reports: Reports
) -> ReconciliationRead:
    return ReconciliationRead.model_validate(
        asdict(reports.reconcile(actor, company_id, "AR", as_of))
    )


@router.post(
    "/receivables/from-journals", response_model=list[ObligationRead], dependencies=[Depends(csrf)]
)
def recognize_receivables(
    payload: Recognize, actor: Actor, company_id: CompanyScope, service: Service
) -> list[ObligationRead]:
    return [
        ObligationRead.model_validate(asdict(value))
        for value in service.recognize(
            actor, company_id, "AR", payload.journal_id, payload.due_date
        )
    ]


@router.get("/receivables/{resource_id}", response_model=ObligationRead)
def get_receivables(
    resource_id: UUID, as_of: date, actor: Actor, company_id: CompanyScope, service: Service
) -> ObligationRead:
    return ObligationRead.model_validate(
        asdict(service.get(actor, company_id, "AR", resource_id, as_of))
    )


@router.get("/collections", response_model=list[SettlementRead])
def list_collections(
    actor: Actor, company_id: CompanyScope, service: Service, target_id: UUID | None = None
) -> list[SettlementRead]:
    return [
        SettlementRead.model_validate(asdict(value))
        for value in service.settlements(actor, company_id, "AR", target_id)
    ]


@router.get("/collections/{resource_id}", response_model=SettlementRead)
def get_collections(
    resource_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> SettlementRead:
    for value in service.settlements(actor, company_id, "AR"):
        if value.id == resource_id:
            return SettlementRead.model_validate(asdict(value))
    raise ResourceNotFound()


@router.post(
    "/collections", response_model=SettlementRead, status_code=201, dependencies=[Depends(csrf)]
)
def create_collections(
    payload: SettlementCreate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> SettlementRead:
    return SettlementRead.model_validate(
        asdict(service.create(actor, company_id, "AR", key=key, **payload.model_dump()))
    )


@router.post(
    "/collections/{resource_id}/allocations",
    response_model=SettlementRead,
    dependencies=[Depends(csrf)],
)
def allocate_collections(
    resource_id: UUID,
    payload: Allocate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> SettlementRead:
    lines = tuple(Allocation(**line.model_dump()) for line in payload.allocations)
    return SettlementRead.model_validate(
        asdict(
            service.change(
                actor, company_id, "AR", resource_id, payload.expected_version, key, lines
            )
        )
    )


@router.post(
    "/collections/{resource_id}/confirm",
    response_model=SettlementRead,
    dependencies=[Depends(csrf)],
)
def confirm_collections(
    resource_id: UUID,
    payload: Confirm,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> SettlementRead:
    return SettlementRead.model_validate(
        asdict(service.change(actor, company_id, "AR", resource_id, payload.expected_version, key))
    )


@router.get("/payables", response_model=list[ObligationRead])
def list_payables(
    as_of: date, actor: Actor, company_id: CompanyScope, service: Service
) -> list[ObligationRead]:
    return [
        ObligationRead.model_validate(asdict(value))
        for value in service.list(actor, company_id, "AP", as_of)
    ]


@router.get("/payables/aging", response_model=AgingRead)
def aging_payables(
    as_of: date, actor: Actor, company_id: CompanyScope, reports: Reports
) -> AgingRead:
    return AgingRead.model_validate(asdict(reports.aging(actor, company_id, "AP", as_of)))


@router.get("/payables/reconciliation", response_model=ReconciliationRead)
def reconcile_payables(
    as_of: date, actor: Actor, company_id: CompanyScope, reports: Reports
) -> ReconciliationRead:
    return ReconciliationRead.model_validate(
        asdict(reports.reconcile(actor, company_id, "AP", as_of))
    )


@router.post(
    "/payables/from-journals", response_model=list[ObligationRead], dependencies=[Depends(csrf)]
)
def recognize_payables(
    payload: Recognize, actor: Actor, company_id: CompanyScope, service: Service
) -> list[ObligationRead]:
    return [
        ObligationRead.model_validate(asdict(value))
        for value in service.recognize(
            actor, company_id, "AP", payload.journal_id, payload.due_date
        )
    ]


@router.get("/payables/{resource_id}", response_model=ObligationRead)
def get_payables(
    resource_id: UUID, as_of: date, actor: Actor, company_id: CompanyScope, service: Service
) -> ObligationRead:
    return ObligationRead.model_validate(
        asdict(service.get(actor, company_id, "AP", resource_id, as_of))
    )


@router.get("/payments", response_model=list[SettlementRead])
def list_payments(
    actor: Actor, company_id: CompanyScope, service: Service, target_id: UUID | None = None
) -> list[SettlementRead]:
    return [
        SettlementRead.model_validate(asdict(value))
        for value in service.settlements(actor, company_id, "AP", target_id)
    ]


@router.get("/payments/{resource_id}", response_model=SettlementRead)
def get_payments(
    resource_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> SettlementRead:
    for value in service.settlements(actor, company_id, "AP"):
        if value.id == resource_id:
            return SettlementRead.model_validate(asdict(value))
    raise ResourceNotFound()


@router.post(
    "/payments", response_model=SettlementRead, status_code=201, dependencies=[Depends(csrf)]
)
def create_payments(
    payload: SettlementCreate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> SettlementRead:
    return SettlementRead.model_validate(
        asdict(service.create(actor, company_id, "AP", key=key, **payload.model_dump()))
    )


@router.post(
    "/payments/{resource_id}/allocations",
    response_model=SettlementRead,
    dependencies=[Depends(csrf)],
)
def allocate_payments(
    resource_id: UUID,
    payload: Allocate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> SettlementRead:
    lines = tuple(Allocation(**line.model_dump()) for line in payload.allocations)
    return SettlementRead.model_validate(
        asdict(
            service.change(
                actor, company_id, "AP", resource_id, payload.expected_version, key, lines
            )
        )
    )


@router.post(
    "/payments/{resource_id}/confirm", response_model=SettlementRead, dependencies=[Depends(csrf)]
)
def confirm_payments(
    resource_id: UUID,
    payload: Confirm,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Key,
) -> SettlementRead:
    return SettlementRead.model_validate(
        asdict(service.change(actor, company_id, "AP", resource_id, payload.expected_version, key))
    )
