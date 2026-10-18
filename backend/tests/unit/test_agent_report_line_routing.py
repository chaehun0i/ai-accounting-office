"""재무제표 문맥 질문의 항목 선택은 기존 읽기 Tool로만 연결됩니다."""

import pytest
from pydantic import ValidationError

from app.agents.graphs.accounting_question import REPORT_LINE_TYPES, contextual_report_line
from app.llm.contracts import AccountingQuestionRoute
from app.reporting.financial_statements.domain.rules import LINES


def test_every_report_line_is_routable_without_amount_calculation():
    assert REPORT_LINE_TYPES == {line.line_code: line.statement_type for line in LINES}
    for line in LINES:
        question = f"이 기간 {line.label} ({line.line_code}) 항목 금액과 근거를 설명해줘."
        assert contextual_report_line(question) == (line.statement_type, line.line_code)
        route = AccountingQuestionRoute(capability=line.statement_type, line_code=line.line_code)
        assert route.line_code == line.line_code


def test_unknown_or_ambiguous_report_line_is_not_forced_into_a_statement():
    assert contextual_report_line("이 기간 마감 가능한가?") is None
    assert contextual_report_line("ASSETS와 LIABILITIES를 비교해줘") is None
    assert contextual_report_line("UNKNOWN_LINE 금액은?") is None
    with pytest.raises(ValidationError):
        AccountingQuestionRoute(capability="BALANCE_SHEET", line_code="../../ASSETS")
