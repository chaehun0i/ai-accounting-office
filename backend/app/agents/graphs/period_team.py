"""기존 마감·채권·채무 도구를 역할별로 읽고 Controller에서 합칩니다."""

from dataclasses import replace
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict
from typing_extensions import TypedDict

from app.agents.runtime.controller import AccountingAnswer
from app.core.digests import digest
from app.jobs.application.runtime import RuntimeAudit
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


class PeriodTeamState(TypedDict, total=False):
    period_id: str
    plan: dict[str, Any]
    as_of: str
    ar_as_of: str
    ap_as_of: str
    closing: dict[str, Any]
    ar: dict[str, Any]
    ap: dict[str, Any]
    answer: dict[str, Any]
    controller_verdict: Literal["PASS", "REVIEW", "BLOCK"]


TOOL_CODES = (
    "closing.readiness",
    "finance.get_ar_reconciliation",
    "finance.get_ap_reconciliation",
)


class TeamPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_id: UUID
    tools: tuple[str, str, str]


def compose_team_answer(state: PeriodTeamState) -> AccountingAnswer:
    closing, ar, ap = state["closing"], state["ar"], state["ap"]
    ar_difference = Decimal(ar["difference"])
    ap_difference = Decimal(ap["difference"])
    blockers = [
        check["check_code"] for check in closing["checks"] if check["severity"] == "BLOCKER"
    ]
    text = (
        f"Closing Agent: {closing['period_status']} 기간, 차단 {len(blockers)}건"
        + (f" ({', '.join(blockers)})" if blockers else "")
        + f". AR Agent: 채권 보조부 {ar['subledger_amount']}, "
        + f"GL {ar['gl_amount']}, 차이 {ar_difference}."
        + f" AP Agent: 채무 보조부 {ap['subledger_amount']}, "
        + f"GL {ap['gl_amount']}, 차이 {ap_difference}."
    )
    if closing["stale"]:
        text += " 마감 검사가 오래되어 재검사가 필요합니다."
    if blockers or ar_difference or ap_difference or closing["stale"]:
        text += " Controller: 차단·차이 항목을 사람이 검토해야 합니다."
    else:
        text += " Controller: 현재 조회된 검사와 보조부 대사가 일치합니다."
    return AccountingAnswer(
        text=text,
        amount=None,
        resource_id=UUID(closing["run_id"] or closing["period_id"]),
        source_digest=digest(
            {
                "closing": closing["source_digest"],
                "ar": ar,
                "ap": ap,
            }
        ),
        source_ids=[UUID(check["source_id"]) for check in closing["checks"] if check["source_id"]],
    )


def team_verdict(
    state: PeriodTeamState, answer: AccountingAnswer
) -> Literal["PASS", "REVIEW", "BLOCK"]:
    closing, ar, ap = state["closing"], state["ar"], state["ap"]
    if (
        TeamPlan.model_validate(state["plan"])
        != TeamPlan(period_id=UUID(state["period_id"]), tools=TOOL_CODES)
        or state["as_of"] != state["ar_as_of"]
        or state["as_of"] != state["ap_as_of"]
        or closing["period_id"] != state["period_id"]
    ):
        return "BLOCK"
    if closing["blocker_count"] != sum(
        check["severity"] == "BLOCKER" for check in closing["checks"]
    ) or answer != compose_team_answer(state):
        return "BLOCK"
    for result in (ar, ap):
        difference = Decimal(result["subledger_amount"]) - Decimal(result["gl_amount"])
        if Decimal(result["difference"]) != difference:
            return "BLOCK"
        if (result["status"] == "MATCHED") != (difference == 0):
            return "BLOCK"
    if (
        closing["stale"]
        or closing["blocker_count"]
        or any(Decimal(result["difference"]) for result in (ar, ap))
    ):
        return "REVIEW"
    return "PASS"


def build_period_team(
    registry: ToolRegistry,
    context: ToolContext,
    audit: RuntimeAudit,
) -> CompiledStateGraph[PeriodTeamState, None, PeriodTeamState, PeriodTeamState]:
    graph = StateGraph(PeriodTeamState)

    def traced(name: str, fn: Any) -> Any:
        def invoke(state: PeriodTeamState) -> dict[str, Any]:
            step = audit.begin_step(context, name)
            current = replace(context, step_id=step)
            try:
                output = fn(state, current)
            except Exception as error:
                audit.finish_step(current, "FAILED", getattr(error, "code", "NODE_FAILED"))
                raise
            audit.finish_step(current, "SUCCEEDED")
            return cast(dict[str, Any], output)

        return invoke

    def lead(state: PeriodTeamState, current: ToolContext) -> dict[str, Any]:
        # 선택 범위는 현재 실제 Domain READ capability만으로 고정합니다.
        for permission in ("period.read", "receivable.read", "payable.read"):
            registry.authorize(current, permission)
        plan = TeamPlan(period_id=UUID(state["period_id"]), tools=TOOL_CODES)
        return {"plan": plan.model_dump(mode="json")}

    def closing(state: PeriodTeamState, current: ToolContext) -> dict[str, Any]:
        result = registry.execute(
            "closing.readiness", {"period_id": state["period_id"]}, current
        ).model_dump(mode="json")
        return {"closing": result["data"], "as_of": result["as_of"]}

    def ar(state: PeriodTeamState, current: ToolContext) -> dict[str, Any]:
        result = registry.execute(
            "finance.get_ar_reconciliation", {"as_of": state["as_of"]}, current
        ).model_dump(mode="json")
        return {"ar": result["data"], "ar_as_of": result["as_of"]}

    def ap(state: PeriodTeamState, current: ToolContext) -> dict[str, Any]:
        result = registry.execute(
            "finance.get_ap_reconciliation", {"as_of": state["as_of"]}, current
        ).model_dump(mode="json")
        return {"ap": result["data"], "ap_as_of": result["as_of"]}

    def compose(state: PeriodTeamState, current: ToolContext) -> dict[str, Any]:
        return {"answer": compose_team_answer(state).model_dump(mode="json")}

    def control(state: PeriodTeamState, current: ToolContext) -> dict[str, Any]:
        answer = AccountingAnswer.model_validate(state["answer"])
        verdict = team_verdict(state, answer)
        # 역할별 UoW 사이에 원천이 변경되면 이전 결과를 성공으로 확정하지 않습니다.
        latest = {
            "closing": registry.execute(
                "closing.readiness", {"period_id": state["period_id"]}, current
            ).model_dump(mode="json"),
            "ar": registry.execute(
                "finance.get_ar_reconciliation", {"as_of": state["as_of"]}, current
            ).model_dump(mode="json"),
            "ap": registry.execute(
                "finance.get_ap_reconciliation", {"as_of": state["as_of"]}, current
            ).model_dump(mode="json"),
        }
        if (
            latest["closing"]["data"] != state["closing"]
            or latest["ar"]["data"] != state["ar"]
            or latest["ap"]["data"] != state["ap"]
            or any(latest[name]["as_of"] != state["as_of"] for name in ("closing", "ar", "ap"))
        ):
            verdict = "BLOCK"
        return {"controller_verdict": verdict}

    for name, fn in (
        ("accounting_lead", lead),
        ("closing_agent", closing),
        ("ar_agent", ar),
        ("ap_agent", ap),
        ("compose_team_answer", compose),
        ("controller_agent", control),
    ):
        graph.add_node(name, cast(Any, traced(name, fn)))
    graph.add_edge(START, "accounting_lead")
    graph.add_edge("accounting_lead", "closing_agent")
    graph.add_edge("closing_agent", "ar_agent")
    graph.add_edge("closing_agent", "ap_agent")
    graph.add_edge(["ar_agent", "ap_agent"], "compose_team_answer")
    graph.add_edge("compose_team_answer", "controller_agent")
    graph.add_edge("controller_agent", END)
    return graph.compile()
