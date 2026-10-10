from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from app.intake.infrastructure.parser import XLSX_MIME
from app.onboarding.domain.template import read_template
from app.onboarding.infrastructure.template import parse_onboarding
from tests.integration.test_onboarding import apply, preview, save, setup

FIXTURES = Path(__file__).parents[1] / "fixtures" / "onboarding"


def test_native_2025_snapshot_and_derived_draft_regression(api_client):
    original = FIXTURES / "sample-company-2025-v1.xlsx"
    assert (
        sha256(original.read_bytes()).hexdigest()
        == "c4df64f12fc517b73f1ef0c164bdeb541c1039a6c43d8ee3971310b414761d02"
    )
    content = (FIXTURES / "onboarding-syn-mfg-2025-derived-v1.xlsx").read_bytes()
    _, expected, errors = read_template(parse_onboarding("onboarding.xlsx", content, XLSX_MIME))
    assert not errors and len(expected) == 425
    headers, current = setup(api_client)
    current = save(
        api_client, headers, current, [("Company.company_name", "singleton", "수동 검토 회사")]
    )
    response = api_client.post(
        "/onboarding/imports",
        headers=headers,
        files={"file": ("onboarding.xlsx", content, XLSX_MIME)},
    )
    assert response.status_code == 201, response.text
    draft = preview(api_client, headers, current, response.json())
    choices = {
        f"{i['incoming']['field_code']}:{i['incoming']['row_key']}": "APPLY_IMPORT"
        for i in draft["items"]
        if i["classification"] == "CONFLICT"
    }
    assert apply(api_client, headers, draft, choices).status_code == 200
    current = api_client.get("/onboarding", headers=headers).json()
    values = {(c["field_code"], c["row_key"]): c for c in current["cells"]}
    for cell in expected:
        actual = values[(cell.field_code, cell.row_key)]
        assert (
            Decimal(str(actual["value"])) == cell.value
            if isinstance(cell.value, Decimal)
            else str(actual["value"]).lower() == str(cell.value).lower()
        )
    assert values[("Company.company_name", "singleton")]["value"] == "가온푸드웍스 주식회사"
    assert values[("Counterparties.role_code", "CUST001")]["value"] == "CUSTOMER"
    assert (
        len({c["row_key"] for c in current["cells"] if c["field_code"] == "COA.account_code"}) == 19
    )
    validation = api_client.post(
        "/onboarding/validate", headers=headers, json={"expected_version": current["version"]}
    )
    assert validation.status_code == 200
    assert any(
        i["validation_code"] == "PENDING_DOMAIN_SUPPORT" for i in validation.json()["issues"]
    )
