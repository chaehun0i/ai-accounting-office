from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.main import create_app
from app.reporting.financial_statements.api.schemas import Generate


def test_reporting_api_requires_company_and_idempotency(settings):
    paths = create_app(settings).openapi()["paths"]
    post = paths["/financial-statements/generate"]["post"]
    assert any(p["name"] == "X-Company-ID" and p["required"] for p in post["parameters"])
    assert any(p["name"] == "Idempotency-Key" and p["required"] for p in post["parameters"])
    assert "/financial-statements/sets/{set_id}" in paths
    assert "/financial-statements/sets/{set_id}/{statement_type}" in paths
    assert "/financial-statements/sets/{set_id}/drilldown" in paths
    with pytest.raises(ValidationError):
        Generate(period_id=uuid4(), status="APPROVED")


def test_metric_read_contract_is_company_scoped(settings):
    operation = create_app(settings).openapi()["paths"]["/financial-metrics"]["get"]
    assert any(p["name"] == "X-Company-ID" and p["required"] for p in operation["parameters"])
    assert any(p["name"] == "period_id" and p["required"] for p in operation["parameters"])
