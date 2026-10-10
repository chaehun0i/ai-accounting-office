from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.journals.api.schemas import (
    JournalCommand,
    JournalCreate,
    JournalRead,
    JournalUpdate,
)
from app.accounting.journals.application.commands import JournalCommands
from app.accounting.journals.application.service import JournalService
from app.accounting.journals.domain.entities import Journal, JournalLine, totals
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf

router = APIRouter(tags=["회계 전표"])


def journal_service(container: Container) -> JournalService:
    if container.journals is None:
        raise DatabaseUnavailable()
    return container.journals


Service = Annotated[JournalService, Depends(journal_service)]


def read(value: Journal) -> JournalRead:
    debit, credit = totals(value.lines)
    return JournalRead.model_validate(
        {
            **asdict(value),
            "total_debit": debit,
            "total_credit": credit,
            "difference": debit - credit,
        }
    )


def draft(
    payload: JournalCreate, company: UUID, actor: Actor, resource: UUID | None = None
) -> Journal:
    now = datetime.now(UTC)
    return Journal(
        id=resource or uuid4(),
        company_id=company,
        accounting_period_id=payload.accounting_period_id,
        entry_date=payload.entry_date,
        description=payload.description,
        source_type=payload.source_type,
        source_transaction_id=payload.source_transaction_id,
        proposal_origin="HUMAN",
        status="DRAFT",
        version=1,
        created_by=actor.user_id,
        created_at=now,
        updated_at=now,
        evidence_ids=tuple(payload.evidence_ids),
        lines=tuple(
            JournalLine(id=uuid4(), line_no=i, **line.model_dump())
            for i, line in enumerate(payload.lines, 1)
        ),
    )


@router.get("/journals", response_model=list[JournalRead])
def listing(
    date_from: date, date_to: date, actor: Actor, company_id: CompanyScope, service: Service
) -> list[JournalRead]:
    return [read(r) for r in service.list(actor, company_id, date_from, date_to)]


@router.get("/journals/{resource_id}", response_model=JournalRead)
def get(resource_id: UUID, actor: Actor, company_id: CompanyScope, service: Service) -> JournalRead:
    return read(service.get(actor, company_id, resource_id))


@router.post("/journals", response_model=JournalRead, status_code=201, dependencies=[Depends(csrf)])
def create(
    payload: JournalCreate,
    actor: Actor,
    company_id: CompanyScope,
    container: Container,
    key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JournalRead:
    if container.journal_commands is None:
        raise DatabaseUnavailable()
    return read(container.journal_commands.create(actor, draft(payload, company_id, actor), key))


@router.patch("/journals/{resource_id}", response_model=JournalRead, dependencies=[Depends(csrf)])
def update(
    resource_id: UUID,
    payload: JournalUpdate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> JournalRead:
    return read(
        service.save(
            actor, draft(payload, company_id, actor, resource_id), payload.expected_version
        )
    )


def commands(container: Container) -> JournalCommands:
    if container.journal_commands is None:
        raise DatabaseUnavailable()
    return container.journal_commands


Commands = Annotated[JournalCommands, Depends(commands)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


@router.post(
    "/journals/{resource_id}/submit", response_model=JournalRead, dependencies=[Depends(csrf)]
)
def submit(
    resource_id: UUID,
    payload: JournalCommand,
    request: Request,
    actor: Actor,
    company_id: CompanyScope,
    service: Commands,
    key: Key,
) -> JournalRead:
    return read(
        service.execute(
            actor,
            company_id,
            resource_id,
            "submit",
            key=key,
            request_id=request.state.request_id,
            **payload.model_dump(),
        )
    )


@router.post(
    "/journals/{resource_id}/request-review",
    response_model=JournalRead,
    dependencies=[Depends(csrf)],
)
def request_review(
    resource_id: UUID,
    payload: JournalCommand,
    request: Request,
    actor: Actor,
    company_id: CompanyScope,
    service: Commands,
    key: Key,
) -> JournalRead:
    return read(
        service.execute(
            actor,
            company_id,
            resource_id,
            "request_review",
            key=key,
            request_id=request.state.request_id,
            **payload.model_dump(),
        )
    )


@router.post(
    "/journals/{resource_id}/approve", response_model=JournalRead, dependencies=[Depends(csrf)]
)
def approve(
    resource_id: UUID,
    payload: JournalCommand,
    request: Request,
    actor: Actor,
    company_id: CompanyScope,
    service: Commands,
    key: Key,
) -> JournalRead:
    return read(
        service.execute(
            actor,
            company_id,
            resource_id,
            "approve",
            key=key,
            request_id=request.state.request_id,
            **payload.model_dump(),
        )
    )


@router.post(
    "/journals/{resource_id}/reject", response_model=JournalRead, dependencies=[Depends(csrf)]
)
def reject(
    resource_id: UUID,
    payload: JournalCommand,
    request: Request,
    actor: Actor,
    company_id: CompanyScope,
    service: Commands,
    key: Key,
) -> JournalRead:
    return read(
        service.execute(
            actor,
            company_id,
            resource_id,
            "reject",
            key=key,
            request_id=request.state.request_id,
            **payload.model_dump(),
        )
    )


@router.post(
    "/journals/{resource_id}/post", response_model=JournalRead, dependencies=[Depends(csrf)]
)
def post(
    resource_id: UUID,
    payload: JournalCommand,
    request: Request,
    actor: Actor,
    company_id: CompanyScope,
    service: Commands,
    key: Key,
) -> JournalRead:
    return read(
        service.execute(
            actor,
            company_id,
            resource_id,
            "post",
            key=key,
            request_id=request.state.request_id,
            **payload.model_dump(),
        )
    )


@router.post(
    "/journals/{resource_id}/reverse", response_model=JournalRead, dependencies=[Depends(csrf)]
)
def reverse(
    resource_id: UUID,
    payload: JournalCommand,
    request: Request,
    actor: Actor,
    company_id: CompanyScope,
    service: Commands,
    key: Key,
) -> JournalRead:
    return read(
        service.execute(
            actor,
            company_id,
            resource_id,
            "reverse",
            key=key,
            request_id=request.state.request_id,
            **payload.model_dump(),
        )
    )


