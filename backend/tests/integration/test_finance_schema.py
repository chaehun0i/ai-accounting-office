"""확정 정산 이력과 회사 외래키를 PostgreSQL에서도 보호합니다."""

from uuid import UUID

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.integration.test_finance_allocations import confirm, make_record, make_source
from tests.integration.test_finance_flow import allocate, finance_setup


@pytest.mark.parametrize("kind", ["AR", "AP"])
def test_confirmed_settlement_is_immutable(api_client, auth_service, kind):
    owner, writer, payload, accounts, cp, connection = finance_setup(api_client, auth_service)
    target = make_source(api_client, owner, writer, payload, accounts, cp, kind, 100)
    path, record = make_record(api_client, owner, writer, payload, accounts, cp, kind, 100)
    record = allocate(api_client, writer, path, record, [(target, 100)])
    response = confirm(api_client, writer, path, record)
    assert response.status_code == 200, response.text
    table = "collections" if kind == "AR" else "payments"
    child = "collection_allocations" if kind == "AR" else "payment_allocations"
    parent_column = "collection_id" if kind == "AR" else "payment_id"
    for statement in (
        f"UPDATE {table} SET reference_no='changed' WHERE id=:id",
        f"DELETE FROM {table} WHERE id=:id",
        f"UPDATE {child} SET allocated_amount=1 WHERE {parent_column}=:id",
        f"DELETE FROM {child} WHERE {parent_column}=:id",
    ):
        # 실패한 SQL은 SAVEPOINT 안에서만 실행하여 나머지 검증을 이어갑니다.
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(text(statement), {"id": UUID(record["id"])})
    result = api_client.get(f"/{path}/{record['id']}", headers=writer).json()
    assert result["status"] == "CONFIRMED"
    assert result["allocations"][0]["allocated_amount"] == "100.0000"


def test_finance_relational_constraints(db_connection):
    inspector = inspect(db_connection)
    for table in (
        "receivables",
        "payables",
        "collections",
        "payments",
        "collection_allocations",
        "payment_allocations",
        "finance_command_receipts",
        "reconciliation_matches",
        "reconciliation_match_lines",
    ):
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert not columns["company_id"]["nullable"]
        assert any("company_id" in index["column_names"] for index in inspector.get_indexes(table))
        assert inspector.get_foreign_keys(table)
        assert inspector.get_check_constraints(table)
        for column in columns.values():
            assert str(column["type"]) not in {"JSON", "JSONB"}
            if column["name"].endswith("_amount"):
                assert (column["type"].precision, column["type"].scale) == (19, 4)
    for table in ("collection_allocations", "payment_allocations"):
        assert (
            sum(len(fk["constrained_columns"]) == 2 for fk in inspector.get_foreign_keys(table))
            >= 2
        )
