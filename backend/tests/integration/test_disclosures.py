"""Disclosure readiness never invents facts when a required source is missing."""

from uuid import uuid4

from tests.integration.test_financial_statements import closed_company


def test_disclosure_generation_blocks_without_statement_set(api_client, auth_service):
    owner, writer, period_id, _, _, _ = closed_company(api_client, auth_service)
    templates = api_client.get("/disclosures/templates", headers=writer)
    assert templates.status_code == 200, templates.text
    assert [item["template_code"] for item in templates.json()] == ["INTERNAL_CORE_NOTES"]
    assert len(templates.json()[0]["sections"]) == 4

    readiness = api_client.get(
        "/disclosures/readiness", headers=owner, params={"period_id": period_id}
    )
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["status"] == "BLOCKED"
    assert "STATEMENT_SET_MISSING" in readiness.json()["issues"]
    assert "CASH_FLOW_SOURCE_REQUIRED" in readiness.json()["issues"]
    assert "EQUITY_SOURCE_REQUIRED" in readiness.json()["issues"]

    generated = api_client.post(
        "/disclosures/instances/generate",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={"period_id": period_id},
    )
    assert generated.status_code == 201, generated.text
    assert generated.json()["status"] == "BLOCKED"
    assert generated.json()["instance_id"] is None
    assert (
        api_client.get(
            "/disclosures/instances", headers=owner, params={"period_id": period_id}
        ).json()
        == []
    )
