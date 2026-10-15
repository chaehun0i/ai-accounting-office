"""조회 응답의 숫자·출처는 Tool 결과 밖으로 나갈 수 없습니다."""

from decimal import Decimal
from uuid import uuid4

from app.agents.runtime.controller import AccountingAnswer, reporting_answer, reporting_verdict


def test_statement_amount_and_evidence_cannot_be_invented():
    statement_set, statement, journal_line = uuid4(), uuid4(), uuid4()
    result = {
        "data": {
            "statement_set_id": str(statement_set),
            "statement_id": str(statement),
            "statement_status": "GENERATED",
            "period_status": "CLOSED",
            "snapshot_digest": "a" * 64,
            "close_version": 1,
            "lines": [
                {"line_code": "NET_PROFIT", "label": "당기순이익", "current_amount": "100.0000"}
            ],
            "sources": [{"journal_line_id": str(journal_line)}],
        }
    }
    answer = reporting_answer("financial_statement.read", result, "NET_PROFIT")
    assert answer.amount == Decimal("100.0000")
    assert reporting_verdict("financial_statement.read", result, "NET_PROFIT", answer) == "PASS"
    assert (
        reporting_verdict(
            "financial_statement.read",
            result,
            "NET_PROFIT",
            answer.model_copy(update={"amount": Decimal("101")}),
        )
        == "BLOCK"
    )
    assert (
        reporting_verdict(
            "financial_statement.read",
            result,
            "NET_PROFIT",
            answer.model_copy(update={"source_ids": [uuid4()]}),
        )
        == "BLOCK"
    )
    assert (
        reporting_verdict(
            "financial_statement.read",
            result,
            "NET_PROFIT",
            answer.model_copy(update={"text": "당기순이익은 999입니다."}),
        )
        == "BLOCK"
    )
    result["data"]["statement_status"] = "DRAFT"
    assert reporting_verdict("financial_statement.read", result, "NET_PROFIT", answer) == "BLOCK"
    result["data"]["statement_status"] = "GENERATED"
    result["data"]["period_status"] = "OPEN"
    assert reporting_verdict("financial_statement.read", result, "NET_PROFIT", answer) == "BLOCK"


def test_closing_answer_uses_exact_status_and_blocker_count():
    period = uuid4()
    result = {
        "data": {
            "period_id": str(period),
            "run_id": None,
            "period_status": "OPEN",
            "blocker_count": 2,
            "stale": False,
            "source_digest": "b" * 64,
            "checks": [],
        }
    }
    answer = reporting_answer("closing.readiness", result, None)
    assert answer.resource_id == period and answer.amount is None
    assert reporting_verdict("closing.readiness", result, None, answer) == "PASS"
    forged = AccountingAnswer.model_validate({**answer.model_dump(), "text": "마감할 수 있습니다."})
    assert reporting_verdict("closing.readiness", result, None, forged) == "BLOCK"
