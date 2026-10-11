"""원본 fixture를 바꾸지 않고 관리차원을 붙인 동일 회계 흐름을 재검증합니다."""

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
