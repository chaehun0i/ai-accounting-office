import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.contracts.errors import (
    ConcurrencyConflict,
    DatabaseUnavailable,
    ForeignKeyConflict,
    IntegrityViolation,
    PersistenceError,
    UniqueConflict,
)
from app.core.database.errors import map_database_error


class DriverError(Exception):
    def __init__(self, state: str) -> None:
        super().__init__("private-password private-sql")
        self.sqlstate = state


@pytest.mark.parametrize(
    "state,kind",
    [
        ("23505", UniqueConflict),
        ("23503", ForeignKeyConflict),
        ("23514", IntegrityViolation),
        ("40001", ConcurrencyConflict),
        ("40P01", ConcurrencyConflict),
        ("08006", DatabaseUnavailable),
    ],
)
def test_sqlstate_mapping_does_not_include_raw_error(
    state: str, kind: type[PersistenceError]
) -> None:
    raw = OperationalError("private-sql", {"value": "private-password"}, DriverError(state))
    mapped = map_database_error(raw)
    assert isinstance(mapped, kind)
    assert "private-password" not in str(mapped)
    assert "private-sql" not in str(mapped)
    assert not hasattr(mapped, "orig")


def test_error_fallbacks() -> None:
    assert isinstance(
        map_database_error(IntegrityError(None, None, Exception())), IntegrityViolation
    )
    assert isinstance(
        map_database_error(OperationalError(None, None, Exception())), DatabaseUnavailable
    )
    assert type(map_database_error(SQLAlchemyError("private-password"))) is PersistenceError
