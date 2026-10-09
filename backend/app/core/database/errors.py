"""SQLSTATE만으로 오류를 변환합니다. SQL·매개변수·연결 주소를 메시지에 넣지 않습니다."""

from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
    StatementError,
)

from app.contracts.errors import (
    ConcurrencyConflict,
    DatabaseUnavailable,
    ForeignKeyConflict,
    IntegrityViolation,
    InvalidPersistenceValue,
    PersistenceError,
    ResourceLocked,
    UniqueConflict,
)


def map_database_error(error: SQLAlchemyError) -> PersistenceError:
    original = getattr(error, "orig", None)
    state = getattr(original, "sqlstate", None)
    if not isinstance(state, str):
        state = ""
    if state == "23505":
        return UniqueConflict()
    if state == "23503":
        return ForeignKeyConflict()
    if state.startswith("23") or isinstance(error, IntegrityError):
        return IntegrityViolation()
    if state in {"40001", "40P01"}:
        return ConcurrencyConflict()
    if state == "55P03":
        return ResourceLocked()
    if state.startswith("08") or state in {"57P01", "57P02", "57P03"}:
        return DatabaseUnavailable()
    if isinstance(error, DBAPIError) and error.connection_invalidated:
        return DatabaseUnavailable()
    if isinstance(error, OperationalError):
        return DatabaseUnavailable()
    if isinstance(error, StatementError) and isinstance(original, ValueError):
        return InvalidPersistenceValue()
    return PersistenceError()
