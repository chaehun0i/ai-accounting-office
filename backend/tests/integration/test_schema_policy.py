from uuid import uuid4

import pytest
from sqlalchemy import Connection, text

from app.core.database.schema import SchemaPolicyError, assert_relational_schema, schema_violations


def test_managed_schema_has_no_json_or_arrays(db_connection: Connection) -> None:
    assert schema_violations(db_connection) == []


def test_guard_reports_json_domains_and_arrays(db_connection: Connection) -> None:
    schema = f"policy_probe_{uuid4().hex}"
    # 이름은 UUID에서만 생성하며 모든 DDL은 테스트 트랜잭션 종료 시 되돌립니다.
    db_connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    db_connection.execute(text(f'CREATE DOMAIN "{schema}".wrapped AS JSONB'))
    db_connection.execute(
        text(
            f'CREATE TABLE "{schema}".probe '
            "(plain JSON, jsonb_value JSONB, wrapped_value "
            f'"{schema}".wrapped, identifiers UUID[], documents JSONB[])'
        )
    )
    violations = schema_violations(db_connection, schemas=(schema,))
    assert {item.column for item in violations} == {
        "plain",
        "jsonb_value",
        "wrapped_value",
        "identifiers",
        "documents",
    }
    with pytest.raises(SchemaPolicyError, match=f"{schema}.probe.plain"):
        assert_relational_schema(db_connection, schemas=(schema,))
    # 다른 스키마의 위반을 프로젝트 public 검사에 섞지 않습니다.
    assert_relational_schema(db_connection)


@pytest.mark.parametrize("schemas", [(), ("pg_catalog",), ("information_schema",)])
def test_system_schemas_are_not_managed(
    db_connection: Connection, schemas: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError):
        schema_violations(db_connection, schemas=schemas)
