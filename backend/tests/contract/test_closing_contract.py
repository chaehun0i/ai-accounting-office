"""결산 명령은 회사·멱등·닫힌 입력을 OpenAPI에서 유지합니다."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.closing.api.schemas import AdjustmentCreate, Finish, Reopen, Start
from app.main import create_app


def test_closing_commands_require_company_and_idempotency(settings):
    paths = create_app(settings).openapi()["paths"]
    for path in (
        "/closing-runs",
        "/closing-runs/{run_id}/checks",
        "/closing-runs/{run_id}/adjustments",
        "/closing-runs/{run_id}/submit",
        "/closing-approvals/{approval_id}/approve",
        "/closing-runs/{run_id}/close",
        "/closing-runs/{run_id}/reopen-request",
        "/closing-runs/{run_id}/reopen",
        "/closing-adjustments/{adjustment_id}/reversal",
    ):
        parameters = paths[path]["post"]["parameters"]
        for header in ("X-Company-ID", "Idempotency-Key"):
            assert any(p["name"] == header and p["required"] for p in parameters)
    assert "/closing/periods" in paths
    assert "/closing-runs/{run_id}/trial-balance" in paths


def test_closing_input_rejects_status_company_and_unknown_adjustment():
    for schema in (Start, AdjustmentCreate, Finish, Reopen):
        assert schema.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        Start(accounting_period_id=uuid4(), company_id=uuid4())
    with pytest.raises(ValidationError):
        Finish(approval_id=uuid4(), status="CLOSED")
    with pytest.raises(ValidationError):
        AdjustmentCreate(
            adjustment_type="TAX_PROVISION",
            entry_date="2026-01-31",
            description="unsupported",
            lines=[{"account_id": str(uuid4()), "debit_amount": "1"}] * 2,
        )
