"""ADR-035의 공식 checkpoint table/column만 격리 스키마에 허용합니다."""

from sqlalchemy import Connection, inspect

from app.core.database.schema import SchemaPolicyError, schema_violations

CHECKPOINT_SCHEMA = "agent_checkpoints"
CHECKPOINT_COLUMNS = {
    "checkpoint_migrations": {"v"},
    "checkpoints": {
        "thread_id",
        "checkpoint_ns",
        "checkpoint_id",
        "parent_checkpoint_id",
        "type",
        "checkpoint",
        "metadata",
    },
    "checkpoint_blobs": {"thread_id", "checkpoint_ns", "channel", "version", "type", "blob"},
    "checkpoint_writes": {
        "thread_id",
        "checkpoint_ns",
        "checkpoint_id",
        "task_id",
        "idx",
        "channel",
        "type",
        "blob",
        "task_path",
    },
}
JSONB_ALLOWLIST = {("checkpoints", "checkpoint"), ("checkpoints", "metadata")}


def assert_framework_schema(connection: Connection, *, require_installed: bool = False) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names(schema=CHECKPOINT_SCHEMA))
    if not tables and not require_installed:
        return
    if tables != set(CHECKPOINT_COLUMNS):
        raise SchemaPolicyError("공식 checkpoint table allowlist와 다릅니다.")
    for table, columns in CHECKPOINT_COLUMNS.items():
        actual = {
            column["name"] for column in inspector.get_columns(table, schema=CHECKPOINT_SCHEMA)
        }
        if actual != columns:
            raise SchemaPolicyError(f"공식 checkpoint column allowlist와 다릅니다: {table}")
    violations = schema_violations(connection, schemas=(CHECKPOINT_SCHEMA,))
    jsonb_columns = {(v.table, v.column) for v in violations if v.data_type == "jsonb"}
    if jsonb_columns != JSONB_ALLOWLIST or any(v.data_type != "jsonb" for v in violations):
        raise SchemaPolicyError("checkpoint JSONB 예외 범위를 벗어났습니다.")
