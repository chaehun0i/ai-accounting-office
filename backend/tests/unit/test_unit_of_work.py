from unittest.mock import MagicMock

import pytest

from app.contracts.unit_of_work import UnitOfWork
from app.core.database.unit_of_work import SQLAlchemyUnitOfWork


def test_success_commits_and_closes() -> None:
    session = MagicMock()
    factory = MagicMock(return_value=session)
    uow: UnitOfWork = SQLAlchemyUnitOfWork(factory)
    with uow:
        pass
    session.begin.assert_called_once()
    session.commit.assert_called_once()
    session.close.assert_called_once()
    session.rollback.assert_not_called()


def test_failure_rolls_back_and_closes() -> None:
    session = MagicMock()
    uow = SQLAlchemyUnitOfWork(MagicMock(return_value=session))
    with pytest.raises(ValueError):
        with uow:
            raise ValueError("업무 검증 실패")
    session.rollback.assert_called_once()
    session.close.assert_called_once()
    session.commit.assert_not_called()
    with pytest.raises(RuntimeError):
        _ = uow.session


def test_commit_failure_rolls_back() -> None:
    session = MagicMock()
    session.commit.side_effect = RuntimeError("확정 실패")
    with pytest.raises(RuntimeError):
        with SQLAlchemyUnitOfWork(MagicMock(return_value=session)):
            pass
    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_explicit_rollback_and_nested_scope() -> None:
    session = MagicMock()
    uow = SQLAlchemyUnitOfWork(MagicMock(return_value=session))
    with uow:
        with pytest.raises(RuntimeError):
            uow.__enter__()
        uow.rollback()
        with pytest.raises(RuntimeError):
            _ = uow.session
    session.commit.assert_not_called()
    session.rollback.assert_called_once()
