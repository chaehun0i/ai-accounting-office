"""원천 조회부터 사람 검토까지 수행하는 명시적 Bookkeeper Graph입니다."""

from collections.abc import Callable
from dataclasses import replace
from typing import Any, Literal, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict
from typing_extensions import TypedDict

from app.agents.runtime.controller import (
    AccountingAnswer,
    reporting_answer,
    reporting_verdict,
    verdict,
)
from app.contracts.access_errors import InvalidInput
from app.contracts.errors import ApplicationError
from app.jobs.application.runtime import RuntimeAudit
from app.llm.contracts import AccountingQuestionRoute, AccountSelection, Classification, LLMError
from app.llm.gateway import LLMGateway
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


class HumanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["CONTINUE", "REJECT"]


class BookkeeperState(TypedDict, total=False):
    run_id: str
    thread_id: str
    company_id: str
    principal_id: str
    transaction_id: str
    source: dict[str, Any]
    evidence_refs: list[str]
    classification: dict[str, Any]
    account_candidates: list[dict[str, Any]]
    proposed_journal: dict[str, Any]
    selection: dict[str, Any]
    validation_errors: list[str]
    controller_verdict: Literal["PASS", "REVIEW", "BLOCK"]
    pending_human_action: str | None
    result_journal_id: str | None
    error_code: str | None


class AccountingQuestionState(TypedDict, total=False):
    question: str
    period_id: str
    route: dict[str, Any]
    tool_code: str
    line_code: str | None
    tool_result: dict[str, Any]
    answer: dict[str, Any]
    controller_verdict: Literal["PASS", "BLOCK"]


def build_bookkeeper(
    registry: ToolRegistry,
    gateway: LLMGateway,
    context: ToolContext,
    audit: RuntimeAudit,
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[BookkeeperState, None, BookkeeperState, BookkeeperState]:
    graph = StateGraph(BookkeeperState)

    def tool(code: str, arguments: dict[str, Any], current: ToolContext) -> dict[str, Any]:
        return registry.execute(code, arguments, current).model_dump(mode="json")

    def load_transaction(state: BookkeeperState, current: ToolContext) -> dict[str, Any]:
        value = tool(
            "accounting.get_transaction", {"transaction_id": state["transaction_id"]}, current
        )
        source = value["data"]
        return {
            "source": {
                key: source[key]
                for key in (
                    "id",
                    "company_id",
                    "version",
                    "accounting_date",
                    "amount",
                    "currency_code",
                    "direction",
                    "source_type",
                    "status",
                )
            }
        }

    def load_evidence(state: BookkeeperState, current: ToolContext) -> dict[str, Any]:
        value = tool(
            "evidence.get_transaction_evidence",
            {"transaction_id": state["transaction_id"]},
            current,
        )
        return {"evidence_refs": value["evidence_refs"]}

    def classify(state: BookkeeperState, current: ToolContext) -> dict[str, Any]:
        import json

        source = state["source"]
        facts = {"source_type": source["source_type"], "direction": source["direction"]}
        value = gateway.generate("classify", json.dumps(facts), Classification)
        return {"classification": value.model_dump(mode="json")}

    def search(state: BookkeeperState, current: ToolContext) -> dict[str, Any]:
        value = tool(
            "accounting.search_accounts",
            {"query_text": state["classification"]["query_text"]},
            current,
        )
        return {"account_candidates": value["data"]}

    def propose(state: BookkeeperState, current: ToolContext) -> dict[str, Any]:
        import json

        if len(state["account_candidates"]) < 2:
            return {"validation_errors": ["ACCOUNT_NOT_FOUND"]}
        facts = {
            "accounts": [
                {k: a[k] for k in ("id", "account_code", "account_name", "account_type")}
                for a in state["account_candidates"]
            ],
            "evidence_ids": state["evidence_refs"],
            "classification": state["classification"],
        }
        try:
            selection = gateway.generate(
                "select_accounts", json.dumps(facts, ensure_ascii=False), AccountSelection
            )
        except LLMError as error:
            if error.code == "OUTPUT_SCHEMA_INVALID":
                return {"validation_errors": ["UNSUPPORTED_PROPOSAL"]}
            raise
        return {"selection": selection.model_dump(mode="json")}

    def arguments(state: BookkeeperState) -> dict[str, Any]:
        return {
            "transaction_id": state["transaction_id"],
            "source_version": state["source"]["version"],
            **state["selection"],
        }

    def validate(state: BookkeeperState, current: ToolContext) -> dict[str, Any]:
        errors = state.get("validation_errors", [])[:]
        if errors:
            return {"validation_errors": errors}
        selection = state["selection"]
        ids = {a["id"] for a in state["account_candidates"]}
        if selection["debit_account_id"] not in ids or selection["credit_account_id"] not in ids:
            errors.append("ACCOUNT_NOT_FOUND")
        if selection["debit_account_id"] == selection["credit_account_id"]:
            errors.append("ACCOUNT_SELECTION_INVALID")
        if set(selection["evidence_ids"]) != set(state["evidence_refs"]):
            errors.append("EVIDENCE_MISMATCH")
        if state["source"]["company_id"] != str(context.company_id):
            errors.append("RESOURCE_NOT_FOUND")
        if errors:
            return {"validation_errors": errors}
        try:
            value = tool("accounting.validate_journal", arguments(state), current)
            return {"proposed_journal": value["data"], "validation_errors": []}
        except ApplicationError as error:
            return {"validation_errors": [error.code]}

    def control(state: BookkeeperState, current: ToolContext) -> dict[str, Any]:
        result = verdict(
            state.get("validation_errors", []),
            bool(state["evidence_refs"]),
            state["classification"]["category"],
        )
        return {
            "controller_verdict": result,
            "pending_human_action": None if result == "BLOCK" else "REVIEW_PROPOSAL",
            "error_code": state.get("validation_errors", [None])[0]
            if state.get("validation_errors")
            else None,
        }

    def human(state: BookkeeperState, current: ToolContext) -> dict[str, Any]:
        response = interrupt(
            {
                "action": "REVIEW_PROPOSAL",
                "verdict": state["controller_verdict"],
                "transaction_id": state["transaction_id"],
            },
            response_schema=HumanDecision,
        )
        decision = HumanDecision.model_validate(response)
        if decision.decision == "REJECT":
            return {"pending_human_action": None, "result_journal_id": None}
        # 재개 시에도 원천·기간·권한을 다시 검증한 후 초안만 생성합니다.
        checked = tool("accounting.validate_journal", arguments(state), current)
        created = tool("accounting.propose_journal", arguments(state), current)
        return {
            "pending_human_action": None,
            "proposed_journal": checked["data"],
            "result_journal_id": created["data"]["id"],
        }

    def traced(
        name: str, fn: Callable[[BookkeeperState, ToolContext], dict[str, Any]]
    ) -> Callable[[BookkeeperState], dict[str, Any]]:
        def invoke(state: BookkeeperState) -> dict[str, Any]:
            step = audit.begin_step(context, name)
            current = replace(context, step_id=step)
            try:
                output = fn(state, current)
            except GraphInterrupt:
                audit.finish_step(current, "WAITING_FOR_INPUT")
                raise
            except Exception as error:
                audit.finish_step(current, "FAILED", getattr(error, "code", "NODE_FAILED"))
                raise
            audit.finish_step(current, "SUCCEEDED")
            return output

        return invoke

    nodes = [
        ("load_transaction", load_transaction),
        ("load_evidence", load_evidence),
        ("classify_transaction", classify),
        ("search_accounts", search),
        ("propose_journal", propose),
        ("validate_proposal", validate),
        ("controller", control),
    ]
    previous = START
    for name, fn in nodes:
        graph.add_node(name, cast(Any, traced(name, fn)))
        graph.add_edge(previous, name)
        previous = name
    graph.add_node("human_review", cast(Any, traced("human_review", human)))
    graph.add_conditional_edges(
        "controller",
        lambda state: state["controller_verdict"],
        {"BLOCK": END, "REVIEW": "human_review", "PASS": "human_review"},
    )
    graph.add_edge("human_review", END)
    return graph.compile(checkpointer=checkpointer)


def build_accounting_question(
    registry: ToolRegistry,
    gateway: LLMGateway,
    context: ToolContext,
    audit: RuntimeAudit,
) -> CompiledStateGraph[
    AccountingQuestionState, None, AccountingQuestionState, AccountingQuestionState
]:
    """기존 Bookkeeper 실행의 읽기 경계로 기간 질의를 처리합니다."""
    import json

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
