"""Company-scoped equity source, readiness and frozen statement API."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf
from app.reporting.equity.service import EquityService

router = APIRouter(prefix="/equity", tags=["자본변동"])


def equity(container: Container) -> EquityService:
    if container.equity is None:
        raise DatabaseUnavailable()
    return container.equity


Service = Annotated[EquityService, Depends(equity)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComponentCreate(Input):
    component_code: str
    name: str
    component_type: Literal[
        "CONTRIBUTED_CAPITAL",
        "RETAINED_EARNINGS",
        "TREASURY_STOCK",
        "OTHER_EQUITY",
        "OCI_COMPONENT",
    ]
    display_order: int = Field(gt=0)


class MappingCreate(Input):
    component_id: UUID
    account_id: UUID
    effective_from: date


class EventCreate(Input):
    journal_line_id: UUID
    event_type: Literal[
        "CAPITAL_CONTRIBUTION",
        "CAPITAL_REDUCTION",
        "DIVIDEND",
        "TREASURY_STOCK_ACQUIRE",
        "TREASURY_STOCK_DISPOSE",
        "PROFIT_TRANSFER",
        "OCI_TRANSFER",
        "OTHER_ADJUSTMENT",
    ]


class DividendCreate(Input):
    resolution_date: date
    payable_date: date | None = None
    total_amount: Decimal = Field(gt=0, max_digits=19, decimal_places=4)
    source_journal_id: UUID | None = None


class PaymentCreate(Input):
    cash_flow_event_id: UUID


class Generate(Input):
    period_id: UUID


@router.get("/components")
def components(actor: Actor, company_id: CompanyScope, service: Service) -> list[dict[str, object]]:
    return service.components(actor, company_id)


@router.post("/components", status_code=201, dependencies=[Depends(csrf)])
def add_component(
    payload: ComponentCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return service.add_component(
        actor,
        company_id,
        payload.component_code,
        payload.name,
        payload.component_type,
        payload.display_order,
    )


@router.get("/mappings")
def mappings(actor: Actor, company_id: CompanyScope, service: Service) -> list[dict[str, object]]:
    return service.mappings(actor, company_id)


@router.post("/mappings", status_code=201, dependencies=[Depends(csrf)])
def map_account(
    payload: MappingCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return service.map_account(
        actor, company_id, payload.component_id, payload.account_id, payload.effective_from
    )


@router.get("/events")
def events(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, object]]:
    return service.events(actor, company_id, period_id)


@router.post("/events", status_code=201, dependencies=[Depends(csrf)])
def classify_event(
    payload: EventCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return service.classify_event(actor, company_id, payload.journal_line_id, payload.event_type)


@router.get("/dividends")
def declarations(
    actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, object]]:
    return service.declarations(actor, company_id)


@router.post("/dividends", status_code=201, dependencies=[Depends(csrf)])
def declare_dividend(
    payload: DividendCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return service.declare_dividend(
        actor,
        company_id,
        payload.resolution_date,
        payload.payable_date,
        payload.total_amount,
        payload.source_journal_id,
    )


@router.get("/dividends/{declaration_id}/payments")
def payments(
    declaration_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, object]]:
    return service.payments(actor, company_id, declaration_id)


@router.post("/dividends/{declaration_id}/payments", status_code=201, dependencies=[Depends(csrf)])
def record_payment(
    declaration_id: UUID,
    payload: PaymentCreate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.record_payment(actor, company_id, declaration_id, payload.cash_flow_event_id)


@router.get("/reconciliation")
def reconciliation(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    from dataclasses import asdict

    return asdict(service.reconciliation(actor, company_id, period_id))


@router.post("/statements/generate", status_code=201, dependencies=[Depends(csrf)])
def generate(
    payload: Generate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> dict[str, object]:
    return service.generate(actor, company_id, payload.period_id, key)


@router.get("/statements")
def snapshots(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, object]]:
    return service.snapshots(actor, company_id, period_id)


@router.get("/statements/{snapshot_id}")
def snapshot(
    snapshot_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return service.snapshot(actor, company_id, snapshot_id)


@router.get("/statements/{snapshot_id}/lines/{line_id}/sources")
def sources(
    snapshot_id: UUID, line_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, object]]:
    return service.drilldown(actor, company_id, snapshot_id, line_id)
