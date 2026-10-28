"""월마감·재무제표 Application 읽기 계약을 Canonical Registry에 연결합니다."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.closing.application.service import ClosingService
from app.closing.domain.entities import ClosingReadiness
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.reporting.cash_flow.service import CashFlowService
from app.reporting.financial_statements.application.service import StatementService
from app.reporting.financial_statements.domain.entities import SourceLine, StatementLine
from app.tools.contracts import Input, Result, ToolContext, ToolDefinition


class ClosingInput(Input):
    period_id: UUID


class StatementInput(Input):
    period_id: UUID
    statement_type: Literal["BALANCE_SHEET", "INCOME_STATEMENT"]
    line_code: str | None = Field(default=None, max_length=60, pattern=r"^[A-Z_]+$")


class CashFlowInput(Input):
    period_id: UUID
    line_code: Literal[
        "OPENING_CASH",
        "NET_PROFIT",
        "NET_OPERATING",
        "NET_INVESTING",
        "NET_FINANCING",
        "EXCHANGE_EFFECT",
        "CLOSING_CASH",
    ]


class ClosingCheck(BaseModel):
    check_code: str
    severity: Literal["PASS", "WARNING", "BLOCKER"]
    amount_impact: Decimal
    source_type: str | None
    source_id: UUID | None
    evidence_ref: UUID | None


class ClosingData(BaseModel):
    period_id: UUID
    period_status: str
    run_id: UUID | None
    run_status: str | None
    close_version: int
    source_digest: str
    stale: bool
    pass_count: int
    warning_count: int
    blocker_count: int
    checks: list[ClosingCheck]


class StatementData(BaseModel):
    period_id: UUID
    period_status: str
    statement_set_id: UUID
    statement_id: UUID
    statement_type: Literal["BALANCE_SHEET", "INCOME_STATEMENT"]
    statement_status: str
    close_version: int
    taxonomy_version: int
    source_digest: str
    snapshot_digest: str
    lines: list[StatementLine]
    sources: list[SourceLine]


class CashFlowData(BaseModel):
    period_id: UUID
    statement_id: UUID
    statement_status: str
    close_version: int
    source_digest: str
    snapshot_digest: str
    line_code: str
    amount: Decimal
    source_ids: list[UUID]


def definitions(
    closing: ClosingService, statements: StatementService, cash_flow: CashFlowService | None = None
) -> tuple[ToolDefinition, ...]:
    def readiness(context: ToolContext, raw: BaseModel) -> BaseModel:
        query = ClosingInput.model_validate(raw)
        value: ClosingReadiness = closing.readiness(
            context.principal, context.company_id, query.period_id
        )
        checks = [ClosingCheck.model_validate(check.__dict__) for check in value.checks]
        data = ClosingData(
            period_id=value.period_id,
            period_status=value.period_status,
            run_id=value.run_id,
            run_status=value.run_status,
            close_version=value.close_version,
            source_digest=value.source_digest,
            stale=value.stale,
            pass_count=sum(check.severity == "PASS" for check in checks),
            warning_count=sum(check.severity == "WARNING" for check in checks),
            blocker_count=sum(check.severity == "BLOCKER" for check in checks),
            checks=checks,
        )
        refs = [check.evidence_ref for check in checks if check.evidence_ref is not None]
        return Result[ClosingData](as_of=value.period_end, data=data, evidence_refs=refs)

    def statement(context: ToolContext, raw: BaseModel) -> BaseModel:
        query = StatementInput.model_validate(raw)
        readiness = closing.readiness(context.principal, context.company_id, query.period_id)
        if readiness.period_status != "CLOSED" or readiness.stale:
            raise StateConflict()
        sets = statements.sets(context.principal, context.company_id, query.period_id)
        if not sets:
            raise ResourceNotFound()
        current = sets[0]
        if (
            current.close_version != readiness.close_version
            or current.closing_run_id != readiness.run_id
            or current.trial_balance_digest != readiness.tb_digest
        ):
            raise StateConflict()
        view = statements.statement(
            context.principal, context.company_id, current.id, query.statement_type
        )
        if query.line_code is not None and query.line_code not in {
            line.line_code for line in view.lines
        }:
            raise InvalidInput()
        sources = (
            list(
                statements.drilldown(
                    context.principal,
                    context.company_id,
                    current.id,
                    query.statement_type,
                    query.line_code,
                )
            )
            if query.line_code
            else []
        )
        data = StatementData(
            period_id=query.period_id,
            period_status=readiness.period_status,
            statement_set_id=current.id,
            statement_id=view.id,
            statement_type=query.statement_type,
            statement_status=view.status,
            close_version=current.close_version,
            taxonomy_version=current.taxonomy_version,
            source_digest=current.trial_balance_digest,
            snapshot_digest=view.snapshot_digest,
            lines=list(view.lines),
            sources=sources,
        )
        return Result[StatementData](as_of=date.today(), data=data)

    result = (
        ToolDefinition(
            "closing.readiness",
            "현재 회사 회계기간의 마감 상태와 결정론적 검사 결과를 읽습니다.",
            "period.read",
            ClosingInput,
            Result[ClosingData],
            readiness,
        ),
        ToolDefinition(
            "financial_statement.read",
            "마감된 기간의 BS/IS 스냅샷과 요청한 항목의 계정·전표 출처를 읽습니다.",
            "financial_statement.read",
            StatementInput,
            Result[StatementData],
            statement,
        ),
    )
    if cash_flow is None:
        return result

    def cash_statement(context: ToolContext, raw: BaseModel) -> BaseModel:
        query = CashFlowInput.model_validate(raw)
        readiness = closing.readiness(context.principal, context.company_id, query.period_id)
        if readiness.period_status != "CLOSED" or readiness.stale:
            raise StateConflict()
        snapshot = cash_flow.current_snapshot(
            context.principal, context.company_id, query.period_id
        )
        if snapshot.close_version != readiness.close_version:
            raise StateConflict()
        line = next(
            (
                item
                for item in cash_flow.snapshot_lines(
                    context.principal, context.company_id, snapshot.id
                )
                if item.line_code == query.line_code and item.source_type in {"TOTAL", "NET_PROFIT"}
            ),
            None,
        )
        if line is None:
            raise ResourceNotFound()
        trace = cash_flow.snapshot_drilldown(
            context.principal, context.company_id, snapshot.id, line.id
        )
        sources = sorted(
            {
                *(item.journal_id for item in trace.events),
                *(item.journal_id for item in trace.adjustment_sources),
                *(item.journal_id for item in trace.cash_balance_sources),
            }
        )
        data = CashFlowData(
            period_id=query.period_id,
            statement_id=snapshot.id,
            statement_status=snapshot.status,
            close_version=snapshot.close_version,
            source_digest=snapshot.source_digest,
            snapshot_digest=snapshot.snapshot_digest,
            line_code=query.line_code,
            amount=line.amount,
            source_ids=sources,
        )
        return Result[CashFlowData](as_of=readiness.period_end, data=data)

    return (
        *result,
        ToolDefinition(
            "cash_flow.read",
            "마감된 기간의 대사된 현금흐름표 항목과 동결된 전표 출처를 읽습니다.",
            "financial_statement.read",
            CashFlowInput,
            Result[CashFlowData],
            cash_statement,
        ),
    )
