"""Company-scoped read model over immutable financial statement sets."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.reporting.financial_metrics.rules import calculate
from app.reporting.financial_statements.application.service import StatementService

router = APIRouter(prefix="/financial-metrics", tags=["재무비율"])


def reporting(container: Container) -> StatementService:
    if container.statements is None:
        raise DatabaseUnavailable()
    return container.statements


Service = Annotated[StatementService, Depends(reporting)]


class MetricRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_code: str
    formula_version: int
    numerator_line_code: str
    denominator_line_code: str
    numerator: Decimal
    denominator: Decimal
    value: Decimal | None
    status: Literal["AVAILABLE", "ZERO_DENOMINATOR"]
    unit: Literal["RATIO"]


class MetricsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    period_id: UUID
    statement_set_id: UUID
    generated_at: datetime
    balance_sheet_digest: str
    income_statement_digest: str
    metrics: tuple[MetricRead, ...]


@router.get("", response_model=MetricsRead)
def metrics(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> MetricsRead:
    latest, balance, income = service.metric_source(actor, company_id, period_id)
    lines = {
        line.line_code: line.current_amount for view in (balance, income) for line in view.lines
    }
    return MetricsRead(
        company_id=company_id,
        period_id=period_id,
        statement_set_id=latest.id,
        generated_at=latest.generated_at,
        balance_sheet_digest=balance.snapshot_digest,
        income_statement_digest=income.snapshot_digest,
        metrics=tuple(MetricRead.model_validate(metric.__dict__) for metric in calculate(lines)),
    )
