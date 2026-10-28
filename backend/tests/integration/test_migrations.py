from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, func, inspect, select, text

from app import model_registry  # noqa: F401
from app.core.database.base import Base
from app.core.database.schema import assert_relational_schema


def test_empty_database_migration_lifecycle(db_connection: Connection) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["connection"] = db_connection
    # 전용 테스트 DB라도 업무 테이블이 있으면 삭제하지 않고 검증을 중단합니다.
    expected = set(Base.metadata.tables) | {"alembic_version"}
    assert set(inspect(db_connection).get_table_names(schema="public")) <= expected
    # 016은 회사 데이터가 아닌 고정 KR_INTERNAL taxonomy v1과 표시 항목을 seed합니다.
    # 나머지 업무 데이터는 여전히 비어 있어야 downgrade 검증을 시작할 수 있습니다.
    reference_rows = {"report_taxonomies": 1, "report_lines": 18}
    for table in Base.metadata.sorted_tables:
        if inspect(db_connection).has_table(table.name):
            assert db_connection.scalar(
                select(func.count()).select_from(table)
            ) == reference_rows.get(table.name, 0)
    db_connection.commit()
    command.downgrade(config, "base")
    db_connection.execute(text("DROP TABLE IF EXISTS public.alembic_version"))
    db_connection.commit()
    assert inspect(db_connection).get_table_names(schema="public") == []
    db_connection.commit()
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.current(config, check_heads=True)
    command.check(config)
    command.downgrade(config, "011_accounting_dimensions")
    assert "import_promotion_rows" not in inspect(db_connection).get_table_names(schema="public")
    db_connection.commit()
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "010_agent_runtime_foundation")
    assert "accounting_dimensions" not in inspect(db_connection).get_table_names(schema="public")
    db_connection.commit()
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "009_finance_subledger")
    assert "agent_runs" not in inspect(db_connection).get_table_names(schema="public")
    db_connection.commit()
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "008_governance")
    assert "receivables" not in inspect(db_connection).get_table_names(schema="public")
    db_connection.commit()
    command.upgrade(config, "head")
    command.check(config)
    migration = MigrationContext.configure(db_connection, opts={"compare_type": True})
    assert migration.get_current_heads() == ("027_cash_flow_snapshots",)
    assert compare_metadata(migration, Base.metadata) == []
    assert_relational_schema(db_connection)
    assert set(inspect(db_connection).get_table_names(schema="public")) == expected
    db_connection.commit()
    command.downgrade(config, "db_foundation")
    assert set(inspect(db_connection).get_table_names(schema="public")) == {"alembic_version"}
    db_connection.commit()
    command.upgrade(config, "001_identity")
    assert set(inspect(db_connection).get_table_names(schema="public")) == {
        "users",
        "refresh_sessions",
        "identity_security_events",
        "alembic_version",
    }
    db_connection.commit()
    command.upgrade(config, "002_tenant_company_rbac")
    assert len(inspect(db_connection).get_table_names(schema="public")) == 11
    db_connection.commit()
    command.upgrade(config, "003_master_accounting_settings")
    command.downgrade(config, "002_tenant_company_rbac")
    assert len(inspect(db_connection).get_table_names(schema="public")) == 11
    db_connection.commit()
    command.upgrade(config, "head")
    command.downgrade(config, "004_storage_evidence_intake")
    assert "onboarding_sessions" not in inspect(db_connection).get_table_names(schema="public")
    db_connection.commit()
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "003_master_accounting_settings")
    assert "imports" not in inspect(db_connection).get_table_names(schema="public")
    db_connection.commit()
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    assert MigrationContext.configure(db_connection).get_current_heads() == ()
    db_connection.commit()
    command.upgrade(config, "head")
