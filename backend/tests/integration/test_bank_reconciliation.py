"""기존 인테이크와 실제 PostgreSQL 대사 명령을 연결합니다."""

from uuid import uuid4

import pytest

from tests.integration.test_finance_flow import finance_setup
from tests.integration.test_intake_api import confirm, preview

CSV = b"source_id,date,amount,currency,direction,description\nb1,2026-01-02,100,KRW,IN,receipt\n"


def prepare_bank(client, auth_service, content=CSV):
    owner, writer, _, accounts, _, _ = finance_setup(client, auth_service)
    account = client.post(
        "/bank-accounts",
        headers=owner,
        json={
            "institution_code": "TEST",
            "alias": "운영 계좌",
            "control_account_id": accounts["보통예금"],
        },
    )
    assert account.status_code == 201, account.text
    upload = client.post(
        "/imports",
        headers=writer,
        data={"source_type": "BANK_TRANSACTION", "target_context": "BANK_SOURCE"},
        files={"file": ("bank.csv", content, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    value = upload.json()
    draft = preview(client, writer, value)
    assert draft["valid"], draft
    receipt = confirm(client, writer, value, draft)
    assert receipt.status_code == 200, receipt.text
    receipt = receipt.json()
    payload = {
        "account_id": account.json()["id"],
        "import_id": value["id"],
        "receipt_id": receipt["id"],
        "source_digest": receipt["source_digest"],
        "confirmed_version": receipt["confirmed_version"],
        "statement_start": "2026-01-01",
        "statement_end": "2026-01-31",
        "opening_balance": "0",
        "closing_balance": "100",
    }
    return owner, writer, payload


def target(client, writer, amount="100", source_id="b1"):
    result = client.post(
        "/transactions",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={
            "transaction_date": "2026-01-02",
            "accounting_date": "2026-01-02",
            "description": "입금 사실",
            "amount": amount,
            "direction": "INFLOW",
            "source_id": source_id,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def command(client, writer, url, payload, key=None):
    return client.post(
        url, headers={**writer, "Idempotency-Key": key or str(uuid4())}, json=payload
    )


def test_confirmed_intake_match_retry_unmatch_and_summary(api_client, auth_service):
    owner, writer, payload = prepare_bank(api_client, auth_service)
    transaction = target(api_client, writer)
    key = str(uuid4())
    result = command(api_client, writer, "/bank-statements/imports", payload, key)
    assert result.status_code == 200, result.text
    statement = result.json()
    assert command(api_client, writer, "/bank-statements/imports", payload, key).json() == statement
    candidates = api_client.post(
        f"/bank-statements/{statement['id']}/match-candidates", headers=writer
    )
    assert candidates.status_code == 200, candidates.text
    candidate = next(c for c in candidates.json() if c["target_id"] == transaction["id"])
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
                    "target_id": candidate["target_id"],
                    "amount": "100",
                    "source_version": candidate["source_version"],
                    "target_version": candidate["target_version"],
                }
            ]
        },
    )
    assert match.status_code == 201, match.text
    match = match.json()
    key = str(uuid4())
    body = {"expected_version": match["version"]}
    url = f"/reconciliations/{match['id']}/confirm"
    confirmed = command(api_client, writer, url, body, key)
    assert confirmed.status_code == 200, confirmed.text
    assert command(api_client, writer, url, body, key).json() == confirmed.json()
    assert command(api_client, writer, url, {"expected_version": 999}, key).status_code == 409
    sources = api_client.get(
        f"/bank-statements/{statement['id']}/transactions", headers=writer
    ).json()
    assert len(sources) == 1 and sources[0]["reconciliation_status"] == "MATCHED"
    summary = api_client.get(f"/bank-statements/{statement['id']}/summary", headers=writer)
    assert summary.status_code == 200, summary.text
    assert summary.json()["blocker"] is True
    assert summary.json()["difference_amount"] == "100.0000"
    unmatch_url = f"/reconciliations/{match['id']}/unmatch"
    body = {"expected_version": confirmed.json()["version"], "reason": ""}
    assert command(api_client, writer, unmatch_url, body).status_code == 422
    body["reason"] = "잘못 연결한 거래 해제"
    removed = command(api_client, writer, unmatch_url, body)
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "UNMATCHED"
    foreign = {**writer, "X-Company-ID": str(uuid4())}
    assert api_client.get(f"/bank-statements/{statement['id']}", headers=foreign).status_code == 404


def test_statement_balance_failure_is_atomic(api_client, auth_service):
    _, writer, payload = prepare_bank(api_client, auth_service)
    payload["closing_balance"] = "999"
    result = command(api_client, writer, "/bank-statements/imports", payload)
    assert result.status_code == 422, result.text
    assert result.json()["code"] == "BANK_STATEMENT_NOT_BALANCED"
    assert api_client.get("/bank-statements", headers=writer).json() == []
    payload["closing_balance"] = "100"
    result = command(api_client, writer, "/bank-statements/imports", payload)
    assert result.status_code == 200, result.text


@pytest.mark.parametrize(
    "source_amounts,target_amounts,expected_type,expected_status",
    [
        (["100"], ["60", "40"], "ONE_TO_MANY", "MATCHED"),
        (["60", "40"], ["100"], "MANY_TO_ONE", "MATCHED"),
        (["100"], ["60"], "ONE_TO_ONE", "PARTIAL"),
    ],
)
def test_multiple_and_partial_reconciliation(
    api_client, auth_service, source_amounts, target_amounts, expected_type, expected_status
):
    content = (
        b"source_id,date,amount,currency,direction,description\n"
        + "".join(
            f"bank-{index},2026-01-02,{amount},KRW,IN,receipt\n"
            for index, amount in enumerate(source_amounts)
        ).encode()
    )
    _, writer, payload = prepare_bank(api_client, auth_service, content)
    transactions = [
        target(api_client, writer, amount, f"target-{index}")
        for index, amount in enumerate(target_amounts)
    ]
    response = command(api_client, writer, "/bank-statements/imports", payload)
    assert response.status_code == 200, response.text
    statement = response.json()
    rows = api_client.get(f"/bank-statements/{statement['id']}/transactions", headers=writer).json()
    candidates = api_client.post(
        f"/bank-statements/{statement['id']}/match-candidates", headers=writer
    ).json()
    pairs = (
        [
            (rows[0], transaction, amount)
            for transaction, amount in zip(transactions, target_amounts, strict=True)
        ]
        if len(rows) == 1
        else [(row, transactions[0], row["amount"]) for row in rows]
    )
    lines = []
    for source, transaction, amount in pairs:
        candidate = next(
            value
            for value in candidates
            if value["source_id"] == source["id"] and value["target_id"] == transaction["id"]
        )
        lines.append(
            {
                "source_type": "BANK",
                "source_id": source["id"],
                "target_type": "TRANSACTION",
                "target_id": transaction["id"],
                "amount": amount,
                "source_version": candidate["source_version"],
                "target_version": candidate["target_version"],
            }
        )
    draft = command(api_client, writer, "/reconciliations", {"lines": lines})
    assert draft.status_code == 201, draft.text
    assert draft.json()["match_type"] == expected_type
    result = command(
        api_client,
        writer,
        f"/reconciliations/{draft.json()['id']}/confirm",
        {"expected_version": draft.json()["version"]},
    )
    assert result.status_code == 200, result.text
    rows = api_client.get(f"/bank-statements/{statement['id']}/transactions", headers=writer).json()
    assert all(row["reconciliation_status"] == expected_status for row in rows)


def test_stale_candidate_and_overmatch_are_blocked(api_client, auth_service):
    _, writer, payload = prepare_bank(api_client, auth_service)
    target(api_client, writer)
    statement = command(api_client, writer, "/bank-statements/imports", payload).json()
    candidate = api_client.post(
        f"/bank-statements/{statement['id']}/match-candidates", headers=writer
    ).json()[0]
    line = {
        "source_type": "BANK",
        "source_id": candidate["source_id"],
        "target_type": candidate["target_type"],
        "target_id": candidate["target_id"],
        "amount": "101",
        "source_version": candidate["source_version"],
        "target_version": candidate["target_version"],
    }
    exceeded = command(api_client, writer, "/reconciliations", {"lines": [line]})
    assert exceeded.status_code == 422, exceeded.text
    assert exceeded.json()["code"] == "RECONCILIATION_AMOUNT_EXCEEDED"
    line["amount"] = "100"
    first = command(api_client, writer, "/reconciliations", {"lines": [line]}).json()
    second = command(api_client, writer, "/reconciliations", {"lines": [line]}).json()
    result = command(
        api_client,
        writer,
        f"/reconciliations/{first['id']}/confirm",
        {"expected_version": first["version"]},
    )
    assert result.status_code == 200, result.text
    stale = command(
        api_client,
        writer,
        f"/reconciliations/{second['id']}/confirm",
        {"expected_version": second["version"]},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "RECONCILIATION_SOURCE_STALE"
