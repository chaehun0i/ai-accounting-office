"""테스트 전용 PostgreSQL에서 업무 테이블·JSON·FK 무결성을 실측합니다."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import model_registry  # noqa: F401
from app.core.config import Settings
from app.core.database.base import Base
from app.core.database.engine import create_database_engine
from pydantic import SecretStr
from sqlalchemy import and_, func, inspect, select, text


def main() -> None:
    from sqlalchemy.engine import make_url

    address = os.environ["TEST_POSTGRES_URL"]
    if not (make_url(address).database or "").endswith("_test"):
        raise ValueError("테스트 전용 DB 주소를 사용해 주세요.")
    settings = Settings(
        _env_file=None,
        app_environment="test",
        postgres_url=SecretStr(address),
        redis_url=SecretStr("redis://localhost:6379/0"),
    )
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names(schema="public")) - {
                "alembic_version"
            }
            assert tables == set(Base.metadata.tables)
            print("business_tables=" + str(len(tables)))
            for kind in ("json", "jsonb"):
                count = connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema='public' AND data_type=:kind"
                    ),
                    {"kind": kind},
                )
                print(kind + "_columns=" + str(count))
                assert count == 0
            foreign_keys = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE contype='f' "
                    "AND connamespace='public'::regnamespace"
                )
            )
            orphan = 0
            for table in Base.metadata.tables.values():
                for constraint in table.foreign_key_constraints:
                    target = constraint.referred_table.alias("fk_target")
                    pairs = [
                        (item.parent, target.c[item.column.name])
                        for item in constraint.elements
                    ]
                    join = and_(*(left == right for left, right in pairs))
                    orphan += (
                        connection.scalar(
                            select(func.count())
                            .select_from(table.outerjoin(target, join))
                            .where(
                                and_(*(left.is_not(None) for left, _ in pairs)),
                                next(iter(target.primary_key)).is_(None),
                            )
                        )
                        or 0
                    )
            print("foreign_keys=" + str(foreign_keys))
            print("orphan_rows=" + str(orphan))
            assert orphan == 0
            print(
                "migration_head="
                + str(
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
