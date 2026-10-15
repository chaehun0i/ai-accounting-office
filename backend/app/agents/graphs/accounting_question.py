"""읽기 전용 기간 질의를 Bookkeeper 거래 제안 Graph와 분리합니다."""

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Literal, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict

from app.agents.runtime.controller import AccountingAnswer, reporting_answer, reporting_verdict
from app.contracts.access_errors import InvalidInput
from app.jobs.application.runtime import RuntimeAudit
from app.llm.contracts import AccountingQuestionRoute
from app.llm.gateway import LLMGateway
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


class AccountingQuestionState(TypedDict, total=False):
    question: str
    period_id: str
    route: dict[str, Any]
    tool_code: str
    line_code: str | None
    tool_result: dict[str, Any]
    answer: dict[str, Any]
    controller_verdict: Literal["PASS", "BLOCK"]


def build_accounting_question(
    registry: ToolRegistry,
    gateway: LLMGateway,
    context: ToolContext,
    audit: RuntimeAudit,
) -> CompiledStateGraph[
    AccountingQuestionState, None, AccountingQuestionState, AccountingQuestionState
]:
    """기존 Registry와 RuntimeAudit를 사용해 기간 질의를 처리합니다."""
    graph = StateGraph(AccountingQuestionState)

    def route(state: AccountingQuestionState, current: ToolContext) -> dict[str, Any]:
        selected = gateway.generate(
            "route_accounting_question",
            json.dumps({"question": state["question"]}, ensure_ascii=False),
            AccountingQuestionRoute,
        )
        return {"route": selected.model_dump(mode="json")}

    def read(state: AccountingQuestionState, current: ToolContext) -> dict[str, Any]:
        selected = state["route"]
        if selected["capability"] == "UNSUPPORTED":
            raise InvalidInput()
        if selected["capability"] == "CLOSING":
            code, line = "closing.readiness", None
            arguments: dict[str, object] = {"period_id": state["period_id"]}
        else:
            code = "financial_statement.read"
            line = selected["line_code"] or (
                "ASSETS" if selected["capability"] == "BALANCE_SHEET" else "NET_PROFIT"
            )
            arguments = {
                "period_id": state["period_id"],
                "statement_type": selected["capability"],
                "line_code": line,
            }
        value = registry.execute(code, arguments, current).model_dump(mode="json")
        return {"tool_code": code, "line_code": line, "tool_result": value}

    def compose(state: AccountingQuestionState, current: ToolContext) -> dict[str, Any]:
        answer = reporting_answer(state["tool_code"], state["tool_result"], state["line_code"])
        return {"answer": answer.model_dump(mode="json")}

    def control(state: AccountingQuestionState, current: ToolContext) -> dict[str, Any]:
        answer = AccountingAnswer.model_validate(state["answer"])
        return {
            "controller_verdict": reporting_verdict(
                state["tool_code"], state["tool_result"], state["line_code"], answer
            )
        }

    def traced(
        name: str,
        fn: Callable[[AccountingQuestionState, ToolContext], dict[str, Any]],
    ) -> Any:
        def invoke(state: AccountingQuestionState) -> dict[str, Any]:
            step = audit.begin_step(context, name)
            current = replace(context, step_id=step)
            try:
                output = fn(state, current)
            except Exception as error:
                audit.finish_step(current, "FAILED", getattr(error, "code", "NODE_FAILED"))
                raise
            audit.finish_step(current, "SUCCEEDED")
            return output

        return invoke

    nodes = (
        ("route_reporting_question", route),
        ("read_reporting_tool", read),
        ("compose_reporting_answer", compose),
        ("control_reporting_answer", control),
    )
    previous = START
    for name, fn in nodes:
        graph.add_node(name, cast(Any, traced(name, fn)))
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()
