"""BS/IS 생성은 회사 권한과 CSRF를 거친 명시적 command입니다."""

from dataclasses import asdict
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf
from app.reporting.financial_statements.api.schemas import (
    Generate,
    MappingCreate,
    MappingRead,
    SourceRead,
    StatementRead,
    StatementSetRead,
)
from app.reporting.financial_statements.application.service import StatementService

router = APIRouter(prefix="/financial-statements", tags=["재무제표"])


def reporting(container: Container) -> StatementService:
    if container.statements is None:
        raise DatabaseUnavailable()
    return container.statements


Service = Annotated[StatementService, Depends(reporting)]
Kind = Literal["BALANCE_SHEET", "INCOME_STATEMENT"]


@router.post("/mappings", response_model=MappingRead, status_code=201, dependencies=[Depends(csrf)])
def map_account(
    payload: MappingCreate, actor: Actor, company_id: CompanyScope, service: Service
) -> MappingRead:
    account, code = service.map_account(
        actor, company_id, payload.period_id, payload.account_id, payload.line_code
    )
    return MappingRead(account_id=account, line_code=code)


@router.get("/sets", response_model=list[StatementSetRead])
def sets(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[StatementSetRead]:
    return [
        StatementSetRead.model_validate(asdict(row))
        for row in service.sets(actor, company_id, period_id)
    ]


@router.post(
    "/generate", response_model=StatementSetRead, status_code=201, dependencies=[Depends(csrf)]
)
def generate(
    payload: Generate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> StatementSetRead:
    return StatementSetRead.model_validate(
        asdict(service.generate(actor, company_id, payload.period_id, key))
    )


@router.get("/sets/{set_id}", response_model=StatementSetRead)
def statement_set(
    set_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> StatementSetRead:
    return StatementSetRead.model_validate(asdict(service.set(actor, company_id, set_id)))


@router.get("/sets/{set_id}/drilldown", response_model=list[SourceRead])
def drilldown(
    set_id: UUID,
    statement_type: Kind,
    line_code: str,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> list[SourceRead]:
    return [
        SourceRead.model_validate(asdict(row))
        for row in service.drilldown(actor, company_id, set_id, statement_type, line_code)
    ]


@router.get("/sets/{set_id}/{statement_type}", response_model=StatementRead)
def statement(
    set_id: UUID, statement_type: Kind, actor: Actor, company_id: CompanyScope, service: Service
) -> StatementRead:
    return StatementRead.model_validate(
        asdict(service.statement(actor, company_id, set_id, statement_type))
    )
