"""Read-only resolution of company-specific report dates."""

from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.application.service import AccountingMasterService
from app.contracts.errors import DatabaseUnavailable
from app.reporting.periods.rules import Preset, ResolvedPeriod, Semantics, resolve

router = APIRouter(prefix="/report-periods", tags=["보고기간"])


def accounting(container: Container) -> AccountingMasterService:
    if container.accounting is None:
        raise DatabaseUnavailable()
    return container.accounting


Service = Annotated[AccountingMasterService, Depends(accounting)]


class ResolutionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_preset: Preset
    period_mode: Semantics
    timezone: str
    date_from: date | None
    date_to: date | None
    as_of: date | None
    partial: bool


@router.get("/resolve", response_model=ResolutionRead)
def resolve_period(
    period_preset: Preset,
    period_mode: Semantics,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    date_from: date | None = None,
    date_to: date | None = None,
    as_of: date | None = None,
) -> ResolutionRead:
    timezone, fiscal_start, week_start, opening_date = service.report_period_policy(
        actor, company_id
    )
    value: ResolvedPeriod = resolve(
        period_preset,
        period_mode,
        timezone=timezone,
        fiscal_year_start_month=fiscal_start,
        week_start=week_start,
        now=datetime.now(UTC),
        opening_date=opening_date,
        date_from=date_from,
        date_to=date_to,
        as_of=as_of,
    )
    return ResolutionRead.model_validate(asdict(value))
