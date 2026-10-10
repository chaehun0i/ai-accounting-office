"""공식 2025 합성 샘플의 기초잔액을 장부까지 비교합니다. 원본은 변경하지 않습니다."""

from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.accounting.templates.infrastructure.models import COATemplateAccountModel, COATemplateModel
from app.intake.infrastructure.parser import XLSX_MIME
from app.master_data.counterparties.domain.entities import Counterparty
from app.onboarding.domain.template import read_template
from app.onboarding.infrastructure.template import parse_onboarding
from tests.integration.test_journal_flow import command, prepare
from tests.integration.test_onboarding import save


def test_official_2025_opening_ledger_trial(api_client, auth_service):
    source = Path(__file__).parents[1] / "fixtures/onboarding/sample-company-2025-v1.xlsx"
    assert (
        sha256(source.read_bytes()).hexdigest()
        == "c4df64f12fc517b73f1ef0c164bdeb541c1039a6c43d8ee3971310b414761d02"
    )
    content = (source.parent / "onboarding-syn-mfg-2025-derived-v1.xlsx").read_bytes()
    _, cells, errors = read_template(parse_onboarding("onboarding.xlsx", content, XLSX_MIME))
    assert not errors

    def rows(sheet):
        grouped = {}
        for cell in cells:
            section, field = cell.field_code.split(".", 1)
            if section == sheet:
                grouped.setdefault(cell.row_key, {})[field] = cell.value
        return list(grouped.values())

    coa = rows("COA")
    opening = rows("Opening_Balances")
    template_id = uuid4()
    _, connection = auth_service
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        session.add(
            COATemplateModel(
                id=template_id,
                template_code="SYN_MFG_001_TEST",
                name="공식 합성 샘플",
                version=1,
                status="ACTIVE",
                valid_from=date(2025, 1, 1),
            )
        )
        session.flush()
        for index, row in enumerate(coa):
            session.add(
                COATemplateAccountModel(
                    id=uuid4(),
                    coa_template_id=template_id,
                    account_code=str(row["account_code"]),
                    account_name=row["account_name"],
                    account_type=row["account_type"],
                    normal_balance=row["normal_balance"],
                    posting_allowed=bool(row["posting_allowed"]),
                    display_order=index,
                    is_contra=str(row["account_code"]) == "1590",
                )
            )
        session.commit()
    owner, writer, _, _ = prepare(api_client, auth_service, year=2025, template_id=str(template_id))
    actor = auth_service[0].authenticate(writer["Authorization"].removeprefix("Bearer "))
    api_client.app.state.services.master_data.create_counterparty(
        actor,
        Counterparty(
            company_id=UUID(writer["X-Company-ID"]),
            counterparty_code="SUPP001",
            display_name="가상공급사01",
            legal_name="가상공급사01",
            normalized_legal_name="",
        ),
    )
    workspace = api_client.get("/onboarding", headers=writer).json()
    values = []
    for row in opening:
        day = str(row["as_of_date"])[:10]
        code = str(row["account_code"])
        cp = row.get("counterparty_code") or ""
        key = day + "|" + code + "|" + cp
        for field, value in {
            "as_of_date": day,
            "account_code": code,
            "counterparty_code": cp,
            "debit_amount": str(row["debit_amount"]),
            "credit_amount": str(row["credit_amount"]),
        }.items():
            if value != "":
                values.append(("Opening_Balances." + field, key, value))
    workspace = save(api_client, writer, workspace, values)
    response = api_client.post(
        "/opening-balances/imports",
        headers={**writer, "Idempotency-Key": "golden-opening-v1"},
        json={"expected_version": workspace["version"]},
    )
    assert response.status_code == 201, response.text
    journal = response.json()
    assert (
        Decimal(journal["total_debit"]) == Decimal(journal["total_credit"]) == Decimal("280000000")
    )
    for actor_headers, action in [
        (writer, "submit"),
        (writer, "request-review"),
        (owner, "approve"),
        (owner, "post"),
    ]:
        response = command(api_client, actor_headers, journal, action)
        assert response.status_code == 200, response.text
        journal = response.json()
    trial = api_client.get(
        "/trial-balance", headers=owner, params={"period_id": journal["accounting_period_id"]}
    )
    assert trial.status_code == 200, trial.text
    by_code = {r["account_code"]: r for r in trial.json()}
    assert sum(Decimal(r["period_debit"]) for r in trial.json()) == Decimal("280000000")
    assert sum(Decimal(r["period_credit"]) for r in trial.json()) == Decimal("280000000")
    for row in opening:
        actual = by_code[str(row["account_code"])]
        assert Decimal(actual["period_debit"]) == Decimal(str(row["debit_amount"]))
        assert Decimal(actual["period_credit"]) == Decimal(str(row["credit_amount"]))
        ledger = api_client.get(
            "/ledger",
            headers=owner,
            params={
                "account_id": actual["account_id"],
                "date_from": "2025-01-01",
                "date_to": "2025-01-31",
            },
        )
        assert ledger.status_code == 200, ledger.text
        balance = Decimal(str(row["debit_amount"])) - Decimal(str(row["credit_amount"]))
        if actual["normal_balance"] == "CREDIT":
            balance = -balance
        assert Decimal(ledger.json()[0]["running_balance"]) == balance
