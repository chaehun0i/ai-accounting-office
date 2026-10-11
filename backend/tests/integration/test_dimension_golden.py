"""원본 fixture를 바꾸지 않고 관리차원을 붙인 동일 회계 흐름을 재검증합니다."""

from sqlalchemy import text

from tests.integration import test_finance_full_year, test_finance_golden
from tests.integration.test_dimensions import create_dimension, create_value


def dimension_adapter(monkeypatch, module):
    original = module.post_journal
    selected = None
    count = 0

    def post(client, owner, writer, payload, lines, description="관리차원 회귀"):
        nonlocal selected, count
        if selected is None:
            axis = create_dimension(client, writer, "GOLDEN_DEPT")
            selected = create_value(client, writer, axis)["id"]
        result = original(
            client,
            owner,
            writer,
            payload,
            [{**line, "dimension_value_ids": [selected]} for line in lines],
            description,
        )
        count += 1
        if count > 1 and count % 100:
            return result
        account = lines[0]["account_id"]
        params = {"account_id": account, "date_from": "2025-01-01", "date_to": "2026-12-31"}
        plain = client.get("/ledger", headers=writer, params=params)
        filtered = client.get(
            "/ledger", headers=writer, params={**params, "dimension_value_id": selected}
        )
        assert plain.status_code == filtered.status_code == 200
        assert plain.json() == filtered.json()
        return result

    monkeypatch.setattr(module, "post_journal", post)


def test_dimension_golden_accounting_finance(api_client, auth_service, monkeypatch):
    dimension_adapter(monkeypatch, test_finance_golden)
    test_finance_golden.test_golden_corp_accounting_and_finance(api_client, auth_service)


def test_dimension_native_full_year(api_client, auth_service, monkeypatch):
    dimension_adapter(monkeypatch, test_finance_full_year)
    test_finance_full_year.test_syn_mfg_001_full_year(api_client, auth_service)
    _, connection = auth_service
    base = (
        "SELECT l.company_id,l.account_id,sum(l.debit_amount),sum(l.credit_amount) "
        "FROM journal_lines l JOIN journal_entries j ON j.id=l.journal_entry_id "
        "AND j.company_id=l.company_id "
    )
    tail = "WHERE j.status='POSTED' GROUP BY l.company_id,l.account_id ORDER BY l.account_id"
    plain = connection.execute(text(base + tail)).all()
    dimension = connection.execute(
        text(
            base + "JOIN journal_line_dimensions d ON d.journal_line_id=l.id "
            "AND d.company_id=l.company_id " + tail
        )
    ).all()
    assert plain and plain == dimension
    assert sum(row[2] for row in plain) == sum(row[3] for row in plain)
