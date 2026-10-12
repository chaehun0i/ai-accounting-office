"""기존 사람 승인·부분 정산 사실을 은행 원천과 연결합니다."""

from uuid import uuid4

import pytest

from tests.integration.test_bank_reconciliation import command
from tests.integration.test_finance_flow import (
    allocate,
    create_settlement,
    finance_setup,
    post_journal,
    recognize,
)
from tests.integration.test_intake_api import confirm, preview


@pytest.mark.parametrize("kind", ["AR", "AP"])
def test_bank_matches_confirmed_collection_and_payment(api_client, auth_service, kind):
    owner, writer, payload, accounts, cp, _ = finance_setup(api_client, auth_service)
    ar = kind == "AR"
    control = "매출채권" if ar else "매입채무"
    origin = post_journal(
        api_client,
        owner,
        writer,
        payload,
        [
            {
                "account_id": accounts[control],
                "counterparty_id": cp,
                "debit_amount" if ar else "credit_amount": "100",
            },
            {
                "account_id": accounts["매출" if ar else "소모품비"],
                "credit_amount" if ar else "debit_amount": "100",
            },
        ],
    )
    obligation = recognize(api_client, writer, origin, kind)
    paid = post_journal(
        api_client,
        owner,
        writer,
        payload,
        [
            {"account_id": accounts["보통예금"], "debit_amount" if ar else "credit_amount": "40"},
            {
                "account_id": accounts[control],
                "counterparty_id": cp,
                "credit_amount" if ar else "debit_amount": "40",
            },
        ],
    )
    path, settlement = create_settlement(api_client, writer, paid, kind, "40")
    settlement = allocate(api_client, writer, path, settlement, [(obligation, "40")])
    confirmed = command(
        api_client,
        writer,
        f"/{path}/{settlement['id']}/confirm",
        {"expected_version": settlement["version"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    account = api_client.post(
        "/bank-accounts",
        headers=owner,
        json={
            "institution_code": "TEST",
            "alias": "부분 정산 계좌",
            "control_account_id": accounts["보통예금"],
        },
    ).json()
    csv = (
        "source_id,date,amount,currency,direction\nsettled-1,2026-01-02,40,KRW,"
        + ("IN" if ar else "OUT")
        + "\n"
    ).encode()
    imported = api_client.post(
        "/imports",
        headers=writer,
        data={"source_type": "BANK_TRANSACTION", "target_context": "BANK_SOURCE"},
        files={"file": ("settlement.csv", csv, "text/csv")},
    ).json()
    draft = preview(api_client, writer, imported)
    receipt = confirm(api_client, writer, imported, draft).json()
    statement = command(
        api_client,
        writer,
        "/bank-statements/imports",
        {
            "account_id": account["id"],
            "import_id": imported["id"],
            "receipt_id": receipt["id"],
            "source_digest": receipt["source_digest"],
            "confirmed_version": receipt["confirmed_version"],
            "statement_start": "2026-01-01",
            "statement_end": "2026-01-31",
            "opening_balance": "0",
            "closing_balance": "40" if ar else "-40",
        },
    ).json()
    candidates = api_client.post(
        f"/bank-statements/{statement['id']}/match-candidates", headers=writer
    ).json()
    candidate = next(c for c in candidates if c["target_id"] == settlement["id"])
    assert candidate["target_type"] == ("COLLECTION" if ar else "PAYMENT")
    match = command(
        api_client,
        writer,
        "/reconciliations",
        {
            "lines": [
                {
                    "source_type": "BANK",
                    "source_id": candidate["source_id"],
                    "target_type": candidate["target_type"],
                    "target_id": settlement["id"],
                    "amount": "40",
                    "source_version": candidate["source_version"],
                    "target_version": candidate["target_version"],
                }
            ]
        },
    ).json()
    result = command(
        api_client,
        writer,
        f"/reconciliations/{match['id']}/confirm",
        {"expected_version": match["version"]},
        str(uuid4()),
    )
    assert result.status_code == 200, result.text
    summary = api_client.get(f"/bank-statements/{statement['id']}/summary", headers=writer).json()
    assert not summary["blocker"] and summary["difference_amount"] == "0.0000"
    obligations = "receivables" if ar else "payables"
    remaining = api_client.get(
        f"/{obligations}/{obligation['id']}?as_of=2026-01-31", headers=writer
    ).json()
    assert remaining["outstanding_amount"] == "60.0000" and remaining["status"] == "PARTIAL"
