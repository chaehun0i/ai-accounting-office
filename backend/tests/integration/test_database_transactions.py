import pytest
from sqlalchemy import Connection, text

from app.contracts.errors import UniqueConflict
from app.core.database.session import create_session_factory
from app.core.database.unit_of_work import SQLAlchemyUnitOfWork


def test_postgresql_connect_commit_and_rollback(db_connection: Connection) -> None:
    assert db_connection.scalar(text("SELECT current_setting('TimeZone')")) == "UTC"
    db_connection.commit()
    with db_connection.begin():
        db_connection.execute(text("INSERT INTO foundation_probe VALUES (1)"))
    with pytest.raises(ValueError):
        with db_connection.begin():
            db_connection.execute(text("INSERT INTO foundation_probe VALUES (2)"))
            raise ValueError("되돌리기 검증")
    assert db_connection.scalars(text("SELECT value FROM foundation_probe")).all() == [1]


def test_uow_success_commits(db_connection: Connection) -> None:
    uow = SQLAlchemyUnitOfWork(create_session_factory(db_connection))
    with uow:
        uow.session.execute(text("INSERT INTO foundation_probe VALUES (1)"))
    assert db_connection.scalar(text("SELECT count(*) FROM foundation_probe")) == 1
    with pytest.raises(RuntimeError):
        _ = uow.session


def test_uow_exception_rolls_back(db_connection: Connection) -> None:
    uow = SQLAlchemyUnitOfWork(create_session_factory(db_connection))
    with pytest.raises(ValueError):
        with uow:
            uow.session.execute(text("INSERT INTO foundation_probe VALUES (1)"))
            raise ValueError("업무 검증 실패")
    assert db_connection.scalar(text("SELECT count(*) FROM foundation_probe")) == 0


def test_explicit_commit_finishes_scope(db_connection: Connection) -> None:
    with SQLAlchemyUnitOfWork(create_session_factory(db_connection)) as uow:
        uow.session.execute(text("INSERT INTO foundation_probe VALUES (1)"))
        uow.commit()
        with pytest.raises(RuntimeError):
            _ = uow.session
    assert db_connection.scalar(text("SELECT count(*) FROM foundation_probe")) == 1


def test_explicit_rollback_does_not_commit_on_exit(db_connection: Connection) -> None:
    with SQLAlchemyUnitOfWork(create_session_factory(db_connection)) as uow:
        uow.session.execute(text("INSERT INTO foundation_probe VALUES (1)"))
        uow.rollback()
    assert db_connection.scalar(text("SELECT count(*) FROM foundation_probe")) == 0


def test_deferred_commit_failure_is_safe_and_atomic(db_connection: Connection) -> None:
    db_connection.execute(
        text(
            "CREATE TEMP TABLE deferred_probe (value INTEGER, "
            "UNIQUE (value) DEFERRABLE INITIALLY DEFERRED)"
        )
    )
    db_connection.commit()
    with pytest.raises(UniqueConflict) as caught:
        with SQLAlchemyUnitOfWork(create_session_factory(db_connection)) as uow:
            uow.session.execute(text("INSERT INTO deferred_probe VALUES (1), (1)"))
    assert "INSERT" not in str(caught.value)
    assert caught.value.__suppress_context__
    assert db_connection.scalar(text("SELECT count(*) FROM deferred_probe")) == 0
