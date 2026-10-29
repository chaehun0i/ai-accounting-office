"""Report catalog and generation run commands/queries."""

from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
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

    code: Literal["BALANCE_SHEET", "INCOME_STATEMENT", "FINANCIAL_METRICS", "CASH_FLOW"]
    label: str
    period_mode: Literal["AS_OF", "RANGE"]
    formats: tuple[Literal["PDF", "XLSX", "CSV"], ...]
    can_generate: bool


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_code: Literal["BALANCE_SHEET", "INCOME_STATEMENT", "FINANCIAL_METRICS", "CASH_FLOW"]
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


class ReportArtifactRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    company_id: UUID
    run_id: UUID
    file_name: str
    file_sha256: str
    size_bytes: int
    content_type: str
    created_at: datetime


@router.get("/catalog", response_model=list[ReportCatalogRead])
def catalog(actor: Actor, company_id: CompanyScope, service: Service) -> list[ReportCatalogRead]:
    return [ReportCatalogRead.model_validate(item) for item in service.catalog(actor, company_id)]


@router.post(
    "/generations", status_code=201, response_model=ReportRunRead, dependencies=[Depends(csrf)]
)
def request(
    payload: ReportRequest, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> ReportRunRead:
    run = service.request(actor, company_id, key=key, **payload.model_dump())
    return ReportRunRead.model_validate(asdict(service.generate(actor, company_id, run.id)))


@router.get("/generations", response_model=list[ReportRunRead])
def history(actor: Actor, company_id: CompanyScope, service: Service) -> list[ReportRunRead]:
    return [
        ReportRunRead.model_validate(asdict(item)) for item in service.history(actor, company_id)
    ]


@router.get("/generations/{run_id}", response_model=ReportRunRead)
def detail(run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service) -> ReportRunRead:
    return ReportRunRead.model_validate(asdict(service.get(actor, company_id, run_id)))


@router.post(
    "/generations/{run_id}/execute",
    response_model=ReportRunRead,
    dependencies=[Depends(csrf)],
)
def execute(
    run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> ReportRunRead:
    return ReportRunRead.model_validate(asdict(service.generate(actor, company_id, run_id)))


@router.post(
    "/generations/{run_id}/retry",
    response_model=ReportRunRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def retry(
    run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service, key: Key
) -> ReportRunRead:
    return ReportRunRead.model_validate(asdict(service.retry(actor, company_id, run_id, key)))


@router.get("/generations/{run_id}/artifact", response_model=ReportArtifactRead)
def artifact(
    run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> ReportArtifactRead:
    value = asdict(service.artifact(actor, company_id, run_id))
    value.pop("storage_key")
    return ReportArtifactRead.model_validate(value)


@router.get("/generations/{run_id}/download")
def download(run_id: UUID, actor: Actor, company_id: CompanyScope, service: Service) -> Response:
    content, artifact = service.download(actor, company_id, run_id)
    return Response(
        content,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.file_name}"',
            "X-Content-SHA256": artifact.file_sha256,
        },
    )
