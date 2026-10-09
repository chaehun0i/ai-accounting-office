from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, inspect, text

from app.core.database.base import Base
from app.core.database.schema import assert_relational_schema


def test_empty_database_migration_lifecycle(db_connection: Connection) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["connection"] = db_connection
    # 전용 테스트 DB라도 업무 테이블이 있으면 삭제하지 않고 검증을 중단합니다.
    assert set(inspect(db_connection).get_table_names(schema="public")) <= {"alembic_version"}
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
    migration = MigrationContext.configure(db_connection, opts={"compare_type": True})
    assert migration.get_current_heads() == ("db_foundation",)
    assert compare_metadata(migration, Base.metadata) == []
    assert_relational_schema(db_connection)
    assert set(inspect(db_connection).get_table_names(schema="public")) == {"alembic_version"}
    db_connection.commit()
    command.downgrade(config, "base")
    assert MigrationContext.configure(db_connection).get_current_heads() == ()
    db_connection.commit()
    command.upgrade(config, "head")
