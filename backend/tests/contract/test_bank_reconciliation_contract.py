"""금융 대사 명령의 회사·CSRF·멱등성과 손실 없는 금액 계약입니다."""

import pytest
from pydantic import ValidationError

from app.finance.banking.api.schemas import Confirm, ItemCreate, MatchCreate
from app.main import create_app


def test_reconciliation_command_headers_and_closed_inputs(settings):
    paths = create_app(settings).openapi()["paths"]
    for path in (
        "/bank-statements/imports",
        "/card-transactions/imports",
        "/reconciliations",
        "/reconciliations/{identifier}/confirm",
        "/reconciliations/{identifier}/unmatch",
        "/bank-statements/{identifier}/close",
    ):
        command = paths[path]["post"]
        for header in ("X-Company-ID", "Idempotency-Key"):
            assert any(p["name"] == header and p["required"] for p in command["parameters"])
    for schema in (Confirm, ItemCreate, MatchCreate):
        assert schema.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        Confirm(expected_version=1, status="CONFIRMED")


@pytest.mark.parametrize("value", [True, 1.1, "NaN", "Infinity", "1.00001"])
def test_reconciliation_money_rejects_unsafe_inputs(value):
    with pytest.raises(ValidationError):
        ItemCreate(reason_code="UNKNOWN", amount=value, description="검토 필요")
