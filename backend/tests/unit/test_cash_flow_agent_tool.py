"""Cash Flow Agent numbers come from the frozen Application read model."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.graphs.accounting_question import contextual_report_line
from app.agents.runtime.controller import reporting_answer, reporting_verdict
from app.contracts.access_errors import StateConflict
from app.identity.users.domain.entities import Principal
from app.tools.contracts import ToolContext
from app.tools.reporting import CashFlowInput, definitions


def test_cash_flow_tool_reads_reconciled_snapshot_and_sources():
    company, period, statement, line, journal = (uuid4() for _ in range(5))
    context = ToolContext(Principal(uuid4(), uuid4(), "agent@example.com"), company)
    readiness = SimpleNamespace(
        period_status="CLOSED", stale=False, close_version=2, period_end=date(2026, 1, 31)
    )
    closing = SimpleNamespace(readiness=lambda actor, scoped_company, selected: readiness)
    snapshot = SimpleNamespace(
        id=statement,
        status="RECONCILED",
        close_version=2,
        source_digest="source",
        snapshot_digest="snapshot",
    )
    cash = SimpleNamespace(
        current_snapshot=lambda actor, scoped_company, selected: snapshot,
        snapshot_lines=lambda actor, scoped_company, selected: (
            SimpleNamespace(
                id=line, line_code="NET_OPERATING", source_type="TOTAL", amount=Decimal("12.3400")
            ),
        ),
        snapshot_drilldown=lambda actor, scoped_company, selected, selected_line: SimpleNamespace(
            events=(SimpleNamespace(journal_id=journal),),
            adjustment_sources=(),
            cash_balance_sources=(),
        ),
    )
    tool = definitions(closing, None, cash)[-1]
    result = tool.handler(context, CashFlowInput(period_id=period, line_code="NET_OPERATING"))
    value = result.model_dump(mode="json")
    assert value["data"]["amount"] == "12.3400"
    assert value["data"]["source_ids"] == [str(journal)]
    answer = reporting_answer(tool.tool_code, value, "NET_OPERATING")
    assert answer.amount == Decimal("12.3400")
    assert answer.source_ids == [journal]
    assert reporting_verdict(tool.tool_code, value, "NET_OPERATING", answer) == "PASS"
    assert contextual_report_line("NET_OPERATING 근거") == ("CASH_FLOW", "NET_OPERATING")

    readiness.stale = True
    with pytest.raises(StateConflict):
        tool.handler(context, CashFlowInput(period_id=period, line_code="NET_OPERATING"))
