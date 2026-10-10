from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.transactions.api.schemas import (
    TransactionCreate,
    TransactionRead,
    TransactionUpdate,
)
from app.accounting.transactions.application.service import TransactionService
from app.accounting.transactions.domain.entities import Transaction
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf
from app.intake.domain.digest import digest

router = APIRouter(tags=["거래"])


def transaction_service(container: Container) -> TransactionService:
    if container.transactions is None:
        raise DatabaseUnavailable()
    return container.transactions


Service = Annotated[TransactionService, Depends(transaction_service)]


def read(value: Transaction) -> TransactionRead:
    return TransactionRead.model_validate(asdict(value))


@router.get("/transactions", response_model=list[TransactionRead])
def listing(
    date_from: date, date_to: date, actor: Actor, company_id: CompanyScope, service: Service
) -> list[TransactionRead]:
    return [read(r) for r in service.list(actor, company_id, date_from, date_to)]


@router.get("/transactions/{resource_id}", response_model=TransactionRead)
def get(
    resource_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> TransactionRead:
    return read(service.get(actor, company_id, resource_id))


@router.post(
    "/transactions", response_model=TransactionRead, status_code=201, dependencies=[Depends(csrf)]
)
def create(
    payload: TransactionCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> TransactionRead:
    now = datetime.now(UTC)
    value = Transaction(
        id=uuid4(),
        company_id=company_id,
        source_fingerprint=digest(payload.model_dump(mode="json")),
        status="READY_FOR_ACCOUNTING",
        version=1,
        created_by=actor.user_id,
        created_at=now,
        updated_at=now,
        **payload.model_dump(),
    )
    return read(service.save(actor, value))


@router.patch(
    "/transactions/{resource_id}", response_model=TransactionRead, dependencies=[Depends(csrf)]
)
def update(
    resource_id: UUID,
    payload: TransactionUpdate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> TransactionRead:
    value = service.get(actor, company_id, resource_id)
    return read(
        service.save(
            actor, replace(value, description=payload.description), payload.expected_version
        )
    )
