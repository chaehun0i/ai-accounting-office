"""기존 Golden 숫자를 유지하며 카드 사용과 은행 카드대금 지급을 대사합니다."""

from decimal import Decimal
from uuid import uuid4

from tests.integration.test_bank_reconciliation import command
from tests.integration.test_finance_golden import golden_corp_accounting_and_finance
from tests.integration.test_intake_api import confirm, preview


def test_golden_card_expense_bank_payment_and_zero_payable(api_client, auth_service):
    context = golden_corp_accounting_and_finance(api_client, auth_service, False, True)
    owner = context["owner"]
    writer = context["writer"]
    accounts = context["accounts"]
    for kind, source_id, day, control in [
        ("CARD", "T002", 3, "카드미지급금"),
        ("BANK", "T007", 15, "현금및현금성자산"),
    ]:
        account = api_client.post(
            "/card-accounts" if kind == "CARD" else "/bank-accounts",
            headers=owner,
            json={
                "institution_code": "GOLDEN",
                "alias": f"Golden {kind}",
                "control_account_id": accounts[control],
            },
        )
        assert account.status_code == 201, account.text
        content = (
            "source_id,date,amount,currency,direction,source_status,raw_reference\n"
            + f"{source_id},2026-10-{day:02d},1100000,KRW,OUT,CAPTURED,{source_id}\n"
        ).encode()
        uploaded = api_client.post(
            "/imports",
            headers=writer,
            data={
                "source_type": f"{kind}_TRANSACTION",
                "target_context": f"{kind}_SOURCE",
                "source_system": f"GOLDEN_{kind}",
            },
            files={"file": ("golden.csv", content, "text/csv")},
        )
        assert uploaded.status_code == 201, uploaded.text
        value = uploaded.json()
        draft = preview(api_client, writer, value)
        assert draft["valid"], draft
        receipt = confirm(api_client, writer, value, draft, str(uuid4())).json()
        payload = {
            "account_id": account.json()["id"],
            "import_id": value["id"],
            "receipt_id": receipt["id"],
            "source_digest": receipt["source_digest"],
            "confirmed_version": receipt["confirmed_version"],
        }
        if kind == "BANK":
            payload.update(
                statement_start="2026-10-01",
                statement_end="2026-10-31",
                opening_balance="1100000",
                closing_balance="0",
            )
        result = command(
            api_client,
            writer,
            "/card-transactions/imports" if kind == "CARD" else "/bank-statements/imports",
            payload,
        )
        assert result.status_code == 200, result.text
        if kind == "CARD":
            card_account = account.json()["id"]
            source = result.json()[0]
            candidate_path = f"/card-transactions/{source['id']}/match-candidates"
        else:
            statement = result.json()
            source = api_client.get(
                f"/bank-statements/{statement['id']}/transactions", headers=writer
            ).json()[0]
            candidate_path = f"/bank-statements/{statement['id']}/match-candidates"
        candidates = api_client.post(candidate_path, headers=writer).json()
        target = context["transactions"][source_id]
        candidate = next(value for value in candidates if value["target_id"] == target["id"])
        match = command(
            api_client,
            writer,
            "/reconciliations",
            {
                "lines": [
                    {
                        "source_type": kind,
                        "source_id": source["id"],
                        "target_type": "TRANSACTION",
                        "target_id": target["id"],
                        "amount": "1100000",
                        "source_version": candidate["source_version"],
                        "target_version": candidate["target_version"],
                    }
                ]
            },
        )
        assert match.status_code == 201, match.text
        result = command(
            api_client,
            writer,
            f"/reconciliations/{match.json()['id']}/confirm",
            {"expected_version": match.json()["version"]},
        )
        assert result.status_code == 200, result.text
    report = api_client.get(
        f"/card-accounts/{card_account}/summary?as_of=2026-10-31", headers=writer
    )
    assert report.status_code == 200, report.text
    assert Decimal(report.json()["gl_balance"]) == 0
    assert Decimal(report.json()["source_balance"]) == 0
    assert Decimal(report.json()["reconciled_payment_amount"]) == Decimal("1100000")
    assert report.json()["blocker"] is False
    # 같은 은행 계정의 다른 Golden 거래는 이 작은 명세에 포함되지 않아 차이를 보존합니다.
    summary = api_client.get(f"/bank-statements/{statement['id']}/summary", headers=writer).json()
    assert Decimal(summary["difference_amount"]) == Decimal("-50550000")
    assert summary["blocker"] is True
