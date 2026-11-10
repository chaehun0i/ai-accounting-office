"""비교 재무제표 검토를 기존 Application Service에 위임합니다."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.reporting.comparatives.service import ComparativeStatementsService
from app.tools.contracts import Input, Result, ToolContext, ToolDefinition


class ComparisonInput(Input):
    period_id: UUID
    comparison_period_id: UUID


class ComparisonReadiness(BaseModel):
    status: Literal["READY", "BLOCKED"]
    reasons: list[str]
    source_digest: str | None = None
    supported_statements: list[str]
    unsupported_statements: list[str]


def definition(service: ComparativeStatementsService) -> ToolDefinition:
    def handler(context: ToolContext, raw: BaseModel) -> BaseModel:
        query = ComparisonInput.model_validate(raw)
        data = ComparisonReadiness.model_validate(
            service.readiness(
                context.principal, context.company_id, query.period_id, query.comparison_period_id
            )
        )
        return Result[ComparisonReadiness](as_of=date.today(), warnings=data.reasons, data=data)

    return ToolDefinition(
        "financial_statement.comparison_readiness",
        "당기와 전기의 CLOSED BS/IS 원천 현재성과 비교 가능성을 검증합니다. "
        "승인이나 생성은 수행하지 않습니다.",
        "financial_statement.read",
        ComparisonInput,
        Result[ComparisonReadiness],
        handler,
    )
