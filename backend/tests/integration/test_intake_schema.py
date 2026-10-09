from sqlalchemy import inspect, text

from app.core.database.base import Base
from app.core.database.schema import assert_relational_schema


def test_intake_schema_constraints_and_no_orphans(identity_database):
    names = {
        "storage_objects",
        "evidences",
        "imports",
        "import_sheets",
        "import_columns",
        "import_mappings",
        "import_validation_errors",
        "import_receipts",
        "import_evidences",
        "import_confirmations",
        "import_source_records",
    }
    with identity_database.connect() as connection:
        inspector = inspect(connection)
        assert names <= set(inspector.get_table_names())
        assert_relational_schema(connection)
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema='public' AND data_type IN ('json','jsonb')"
                )
            )
            == 0
        )
        for name in names:
            assert inspector.get_pk_constraint(name)["constrained_columns"]
            assert inspector.get_foreign_keys(name)
            assert not (
                {"payload", "metadata", "context", "extra", "options"}
                & set(Base.metadata.tables[name].c.keys())
            )
            for fk in inspector.get_foreign_keys(name):
                assert fk["options"].get("ondelete") == "RESTRICT"
                # 컬럼 이름은 선언된 메타데이터에서 가져오고 식별자를 인용합니다.
                quote = connection.dialect.identifier_preparer.quote
                child = quote(name)
                parent = quote(fk["referred_table"])
                pairs = list(zip(fk["constrained_columns"], fk["referred_columns"], strict=True))
                present = " AND ".join(f"c.{quote(c)} IS NOT NULL" for c, _ in pairs)
                match = " AND ".join(f"c.{quote(c)} = p.{quote(p)}" for c, p in pairs)
                query = (
                    f"SELECT count(*) FROM {child} c WHERE {present} "
                    f"AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE {match})"
                )
                assert connection.scalar(text(query)) == 0, (name, fk["name"])
            if "company_id" in Base.metadata.tables[name].c:
                assert any(
                    index["column_names"][0] == "company_id"
                    for index in inspector.get_indexes(name)
                )
