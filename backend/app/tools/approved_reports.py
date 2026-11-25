"""Only a human-confirmed request can export an independently approved revision."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.contracts.access_errors import StateConflict
from app.reporting.center.service import ReportCenterService
from app.tools.contracts import Input, Result, ToolContext, ToolDefinition


class ApprovedSetInput(Input):
    period_id: UUID
    approved_snapshot_id: UUID
    expected_version: int = Field(ge=1)
    expected_review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    date_from: date
    date_to: date
    format: Literal["PDF", "XLSX", "CSV"]


class ApprovedReportInput(ApprovedSetInput):
    comparison_period_id: UUID


class ApprovedReportResult(BaseModel):
    report_run_id: UUID
    status: Literal["COMPLETED"]
    source_digest: str


def definition(service: ReportCenterService, *, statement_set: bool = False) -> ToolDefinition:
    input_model = ApprovedSetInput if statement_set else ApprovedReportInput
    report_code = "FINANCIAL_STATEMENT_SET" if statement_set else "COMPARATIVE_FINANCIAL_STATEMENTS"

    def handler(context: ToolContext, raw: BaseModel) -> BaseModel:
        query = input_model.model_validate(raw)
        if context.invocation_id is None:
            raise StateConflict()
        run = service.request(
            context.principal,
            context.company_id,
            report_code=report_code,
            period_preset="CUSTOM",
            key=str(context.invocation_id),
            **query.model_dump(),
        )
        run = service.generate(context.principal, context.company_id, run.id)
        if run.status != "COMPLETED":
            raise StateConflict()
        return Result[ApprovedReportResult](
            as_of=query.date_to,
            data=ApprovedReportResult(
                report_run_id=run.id,
                status="COMPLETED",
                source_digest=run.source_digest,
            ),
        )

    return ToolDefinition(
        "reports.export_approved_set" if statement_set else "reports.export_approved_comparison",
        "사람이 확인한 독립 승인 revision만 Export합니다. 승인·원천을 다시 검증합니다.",
        "report.generate",
        input_model,
        Result[ApprovedReportResult],
        handler,
        tool_class="COMMAND",
        side_effect_level="REPORT",
    )
