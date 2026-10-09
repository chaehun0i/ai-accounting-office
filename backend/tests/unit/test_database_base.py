from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, MetaData, Table

from app.core.database.base import Base
from app.core.database.naming import NAMING_CONVENTION


def test_base_has_no_business_tables() -> None:
    assert not Base.metadata.tables


def test_constraint_names_are_deterministic() -> None:
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    Table("parent", metadata, Column("id", Integer, primary_key=True))
    child = Table(
        "child",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("parent.id"), unique=True),
        CheckConstraint("id > 0", name="positive_id"),
    )
    index = Index(None, child.c.parent_id)
    assert {str(c.name) for c in child.constraints} == {
        "pk_child",
        "fk_child_parent_id_parent",
        "uq_child_parent_id",
        "ck_child_positive_id",
    }
    assert str(index.name) == "ix_child_parent_id"
