"""프로젝트 관리 스키마의 금지 저장 타입을 PostgreSQL catalog로 확인합니다."""

from dataclasses import dataclass

from sqlalchemy import Connection, bindparam, text


@dataclass(frozen=True)
class SchemaViolation:
    schema: str
    table: str
    column: str
    data_type: str


class SchemaPolicyError(ValueError):
    """위반 위치만 제공하며 저장 값이나 접속 정보는 포함하지 않습니다."""


_QUERY = text("""
WITH RECURSIVE column_types AS (
    SELECT n.nspname AS schema_name, c.relname AS table_name,
           a.attname AS column_name, a.atttypid AS type_oid
    FROM pg_catalog.pg_attribute a
    JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN :schemas AND c.relkind IN ('r', 'p')
      AND a.attnum > 0 AND NOT a.attisdropped
    UNION ALL
    SELECT ct.schema_name, ct.table_name, ct.column_name,
           CASE WHEN t.typbasetype <> 0 THEN t.typbasetype ELSE t.typelem END
    FROM column_types ct JOIN pg_catalog.pg_type t ON t.oid = ct.type_oid
    WHERE t.typbasetype <> 0 OR (t.typcategory = 'A' AND t.typelem <> 0)
)
SELECT DISTINCT ct.schema_name, ct.table_name, ct.column_name, t.typname
FROM column_types ct JOIN pg_catalog.pg_type t ON t.oid = ct.type_oid
WHERE t.typname IN ('json', 'jsonb') OR t.typcategory = 'A'
ORDER BY ct.schema_name, ct.table_name, ct.column_name, t.typname
""").bindparams(bindparam("schemas", expanding=True))


def schema_violations(
    connection: Connection,
    *,
    schemas: tuple[str, ...] = ("public",),
) -> list[SchemaViolation]:
    if connection.dialect.name != "postgresql":
        raise ValueError("스키마 정책 검사는 PostgreSQL에서 실행해 주세요.")
    if not schemas or any(
        name.startswith("pg_") or name == "information_schema" for name in schemas
    ):
        raise ValueError("프로젝트가 관리하는 스키마를 명시해 주세요.")
    return [SchemaViolation(*row) for row in connection.execute(_QUERY, {"schemas": schemas})]


def assert_relational_schema(
    connection: Connection,
    *,
    schemas: tuple[str, ...] = ("public",),
) -> None:
    violations = schema_violations(connection, schemas=schemas)
    if violations:
        columns = ", ".join(
            f"{item.schema}.{item.table}.{item.column} ({item.data_type})" for item in violations
        )
        raise SchemaPolicyError(f"관계형 저장 정책을 위반한 컬럼입니다: {columns}")
