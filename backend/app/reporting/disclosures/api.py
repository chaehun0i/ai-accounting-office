"""Company scoped endpoints for Notes readiness, generation and provenance."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf
from app.reporting.disclosures.service import DisclosureService

router = APIRouter(prefix="/disclosures", tags=["재무제표 주석"])


def disclosures(container: Container) -> DisclosureService:
    if container.disclosures is None:
        raise DatabaseUnavailable()
    return container.disclosures


Service = Annotated[DisclosureService, Depends(disclosures)]


class Generate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_id: UUID


class NarrativeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_id: UUID
    text_value: str
    expected_version: int


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int


class Rejection(Transition):
    reason: str


@router.get("/templates")
def templates(actor: Actor, company_id: CompanyScope, service: Service) -> list[dict[str, object]]:
    return service.templates(actor, company_id)


@router.get("/readiness")
def readiness(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return service.readiness(actor, company_id, period_id)


@router.post("/instances/generate", status_code=201, dependencies=[Depends(csrf)])
def generate(
    payload: Generate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> dict[str, object]:
    return service.generate(actor, company_id, payload.period_id, key)


@router.get("/instances")
def instances(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[dict[str, object]]:
    return service.list(actor, company_id, period_id)


@router.get("/instances/{instance_id}")
def instance(
    instance_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return service.detail(actor, company_id, instance_id)


@router.get("/instances/{instance_id}/values/{value_id}/source")
def source(
    instance_id: UUID, value_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> dict[str, object]:
    return service.source(actor, company_id, instance_id, value_id)


@router.put("/instances/{instance_id}/narratives", dependencies=[Depends(csrf)])
def save_narrative(
    instance_id: UUID,
    payload: NarrativeWrite,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.save_narrative(
        actor,
        company_id,
        instance_id,
        payload.section_id,
        payload.text_value,
        payload.expected_version,
    )


@router.post("/instances/{instance_id}/request-review", dependencies=[Depends(csrf)])
def request_review(
    instance_id: UUID,
    payload: Transition,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.request_review(actor, company_id, instance_id, payload.expected_version)


@router.post("/instances/{instance_id}/approve", dependencies=[Depends(csrf)])
def approve(
    instance_id: UUID,
    payload: Transition,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.approve(actor, company_id, instance_id, payload.expected_version)


@router.post("/instances/{instance_id}/reject", dependencies=[Depends(csrf)])
def reject(
    instance_id: UUID,
    payload: Rejection,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> dict[str, object]:
    return service.reject(actor, company_id, instance_id, payload.expected_version, payload.reason)
