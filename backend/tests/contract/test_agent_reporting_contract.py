"""Bookkeeper 기간 질의와 읽기 전용 Canonical Tool 계약."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.api.router import AskAccounting
from app.main import create_app
from app.tools.registry import FORBIDDEN
from app.tools.reporting import ClosingInput, StatementInput, definitions


def test_query_api_and_tool_input_contract(settings):
    post = create_app(settings).openapi()["paths"]["/agent/queries/bookkeeper"]["post"]
    assert any(
        value["name"] == "X-Company-ID" and value["required"] for value in post["parameters"]
    )
    assert any(
        value["name"] == "Idempotency-Key" and value["required"] for value in post["parameters"]
    )
    with pytest.raises(ValidationError):
        AskAccounting(period_id=uuid4(), question="마감 가능한가?", company_id=uuid4())
    with pytest.raises(ValidationError):
        ClosingInput(period_id=uuid4(), sql="SELECT 1")
    with pytest.raises(ValidationError):
        StatementInput(period_id=uuid4(), statement_type="CASH_FLOW")


def test_reporting_tools_are_read_only_and_forbidden_actions_stay_absent():
    codes = {tool.tool_code: tool for tool in definitions(None, None)}  # type: ignore[arg-type]
    assert set(codes) == {"closing.readiness", "financial_statement.read"}
    assert all(
        tool.tool_class == "READ" and tool.side_effect_level == "NONE" for tool in codes.values()
    )
    assert not set(codes).intersection(FORBIDDEN)
    assert codes["closing.readiness"].required_permission == "period.read"
    assert codes["financial_statement.read"].required_permission == "financial_statement.read"
