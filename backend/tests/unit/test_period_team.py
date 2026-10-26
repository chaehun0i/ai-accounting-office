"""역할별 결과를 합칠 때 금액·상태·출처를 임의로 바꾸지 않습니다."""

from datetime import date
from typing import Any, cast
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.agents.graphs.period_team import (
    TOOL_CODES,
    PeriodTeamState,
    TeamPlan,
    build_period_team,
    compose_team_answer,
    team_verdict,
)
from app.identity.users.domain.entities import Principal
from app.jobs.application.runtime import RuntimeAudit
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


def state() -> PeriodTeamState:
    period_id = str(uuid4())
    return PeriodTeamState(
        period_id=period_id,
        plan=TeamPlan(period_id=UUID(period_id), tools=TOOL_CODES).model_dump(mode="json"),
        as_of="2026-01-31",
        ar_as_of="2026-01-31",
        ap_as_of="2026-01-31",
        closing={
            "period_id": period_id,
            "run_id": None,
            "period_status": "CLOSED",
            "source_digest": "a" * 64,
            "blocker_count": 0,
            "stale": False,
            "checks": [],
        },
        ar={
            "status": "MATCHED",
            "subledger_amount": "125.0000",
            "gl_amount": "125.0000",
            "difference": "0.0000",
        },
        ap={
            "status": "MATCHED",
            "subledger_amount": "30.0000",
            "gl_amount": "30.0000",
            "difference": "0.0000",
        },
    )


def test_team_answer_uses_only_tool_facts_and_controller_detects_tampering():
    source = state()
    answer = compose_team_answer(source)
    assert "125.0000" in answer.text and "30.0000" in answer.text
    assert answer.amount is None
    assert team_verdict(source, answer) == "PASS"
    assert team_verdict(source, answer.model_copy(update={"text": "모두 0원입니다."})) == "BLOCK"
    source["ap_as_of"] = "2026-02-01"
    assert team_verdict(source, answer) == "BLOCK"
    source["ap_as_of"] = "2026-01-31"

    source["ar"]["difference"] = "1.0000"
    assert team_verdict(source, compose_team_answer(source)) == "BLOCK"


def test_team_returns_review_for_actual_reconciliation_difference_and_closing_blocker():
    source = state()
    source["ar"].update(status="MISMATCH", gl_amount="124.0000", difference="1.0000")
    assert team_verdict(source, compose_team_answer(source)) == "REVIEW"
    source["closing"]["checks"] = [
        {"check_code": "JOURNAL_PENDING", "severity": "BLOCKER", "source_id": None}
    ]
    source["closing"]["blocker_count"] = 1
    assert "JOURNAL_PENDING" in compose_team_answer(source).text
    assert team_verdict(source, compose_team_answer(source)) == "REVIEW"


def test_team_graph_runs_specialists_in_order_and_rechecks_with_controller():
    source = state()

    class Response(BaseModel):
        as_of: date
        data: dict[str, Any]

    class Registry:
        def __init__(self):
            self.calls: list[str] = []

        def authorize(self, context, permission):
            assert permission in {"period.read", "receivable.read", "payable.read"}

        def execute(self, code, arguments, context):
            self.calls.append(code)
            if code == "closing.readiness":
                assert arguments == {"period_id": source["period_id"]}
                data = source["closing"]
            else:
                assert arguments == {"as_of": source["as_of"]}
                data = source["ar"] if code == "finance.get_ar_reconciliation" else source["ap"]
            return Response(as_of=date(2026, 1, 31), data=data)

    class Audit:
        def __init__(self):
            self.started: list[str] = []
            self.finished: list[str] = []

        def begin_step(self, context, name):
            self.started.append(name)
            return uuid4()

        def finish_step(self, context, status, error=None):
            self.finished.append(status)

    registry, audit = Registry(), Audit()
    actor = Principal(uuid4(), uuid4(), "reviewer@example.com")
    context = ToolContext(actor, uuid4(), uuid4())
    graph = build_period_team(cast(ToolRegistry, registry), context, cast(RuntimeAudit, audit))
    result = graph.invoke(PeriodTeamState(period_id=source["period_id"]))
    assert result["controller_verdict"] == "PASS"
    assert registry.calls.count("closing.readiness") == 2
    assert registry.calls.count("finance.get_ar_reconciliation") == 2
    assert registry.calls.count("finance.get_ap_reconciliation") == 2
    assert {
        "accounting_lead",
        "closing_agent",
        "ar_agent",
        "ap_agent",
        "controller_agent",
    }.issubset(audit.started)
    assert audit.started.index("closing_agent") < audit.started.index("ar_agent")
    assert audit.started.index("ar_agent") < audit.started.index("ap_agent")
    assert audit.started.index("ap_agent") < audit.started.index("controller_agent")
    assert len(audit.finished) == len(audit.started)
