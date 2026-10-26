"""승인 대기 Graph 상태는 검증된 분개 필드만 사용자에게 노출합니다."""

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.runtime.service import AgentRuntime
from app.contracts.access_errors import StateConflict


class Audit:
    def __init__(self, run):
        self.run = run

    def reviewable(self, actor, company, run_id):
        assert run_id == self.run.id
        return self.run


class Saver:
    def __init__(self, values):
        self.values = values

    def get_tuple(self, config):
        return SimpleNamespace(checkpoint={"channel_values": self.values})


def make_runtime():
    company, transaction, run_id, debit, credit = (uuid4() for _ in range(5))
    run = SimpleNamespace(
        id=run_id,
        transaction_id=transaction,
        graph_thread_id=str(run_id),
        version=3,
        controller_verdict="REVIEW",
    )
    values = {
        "company_id": str(company),
        "transaction_id": str(transaction),
        "source": {"version": 2, "secret": "never return"},
        "account_candidates": [
            {"id": str(debit), "account_code": "1010", "account_name": "차변 계정"},
            {"id": str(credit), "account_code": "2010", "account_name": "대변 계정"},
        ],
        "proposed_journal": {
            "entry_date": "2026-01-02",
            "description": "거래 기반 분개 제안",
            "evidence_ids": [],
            "lines": [
                {"account_id": str(debit), "debit_amount": "100.0000", "credit_amount": "0"},
                {"account_id": str(credit), "debit_amount": "0", "credit_amount": "100.0000"},
            ],
            "internal_prompt": "never return",
        },
    }

    @contextmanager
    def open_checkpoint(thread_id):
        assert thread_id == str(run_id)
        yield Saver(values)

    return AgentRuntime(None, None, Audit(run), open_checkpoint), values, company, run_id


def test_preview_exposes_only_typed_proposal():
    runtime, values, company, run_id = make_runtime()
    response = runtime.preview(None, company, run_id).model_dump(mode="json")
    assert response["run_version"] == 3
    assert response["source_version"] == 2
    assert response["lines"][0]["debit_amount"] == "100.0000"
    assert response["lines"][1]["credit_amount"] == "100.0000"
    assert "secret" not in str(response) and "internal_prompt" not in str(response)


def test_preview_rejects_checkpoint_from_another_company():
    runtime, values, company, run_id = make_runtime()
    values["company_id"] = str(uuid4())
    with pytest.raises(StateConflict):
        runtime.preview(None, company, run_id)
