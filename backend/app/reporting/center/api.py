"""Report catalog and generation run commands/queries."""

from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf
from app.reporting.center.service import ReportCenterService
from app.reporting.periods.rules import Preset

router = APIRouter(prefix="/reports", tags=["보고서 센터"])


def center(container: Container) -> ReportCenterService:
    if container.report_center is None:
        raise DatabaseUnavailable()
    return container.report_center


Service = Annotated[ReportCenterService, Depends(center)]


class ReportCatalogRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["BALANCE_SHEET", "INCOME_STATEMENT", "FINANCIAL_METRICS"]
    label: str
    period_mode: Literal["AS_OF", "RANGE"]
    formats: tuple[Literal["PDF", "XLSX", "CSV"], ...]
    can_generate: bool


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_code: Literal["BALANCE_SHEET", "INCOME_STATEMENT", "FINANCIAL_METRICS"]
    format: Literal["PDF", "XLSX", "CSV"]
    period_id: UUID
    period_preset: Preset
    date_from: date | None = None
    date_to: date | None = None
    as_of: date | None = None


class ReportRunRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    company_id: UUID
    report_code: str
    format: str
    period_preset: str
    period_mode: str
    date_from: date | None
    date_to: date | None
    as_of: date | None
    period_id: UUID
    statement_set_id: UUID
    close_version: int
    taxonomy_version: int
    trial_balance_digest: str
    mapping_digest: str
    balance_sheet_digest: str
    income_statement_digest: str
    source_digest: str
    template_version: int
    status: str
    requested_by: UUID
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    retry_of_run_id: UUID | None
    version: int


@router.get("/catalog", response_model=list[ReportCatalogRead])
def catalog(actor: Actor, company_id: CompanyScope, service: Service) -> list[ReportCatalogRead]:
    return [ReportCatalogRead.model_validate(item) for item in service.catalog(actor, company_id)]


@router.post(
    "/generations", status_code=201, response_model=ReportRunRead, dependencies=[Depends(csrf)]
)
def request(
    payload: ReportRequest, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> ReportRunRead:
    return ReportRunRead.model_validate(
        asdict(service.request(actor, company_id, key=key, **payload.model_dump()))
    )


@router.get("/generations", response_model=list[ReportRunRead])
def history(actor: Actor, company_id: CompanyScope, service: Service) -> list[ReportRunRead]:
    return [
        ReportRunRead.model_validate(asdict(item)) for item in service.history(actor, company_id)
    ]


@router.get("/generations/{run_id}", response_model=ReportRunRead)
def detail(run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service) -> ReportRunRead:
    return ReportRunRead.model_validate(asdict(service.get(actor, company_id, run_id)))
