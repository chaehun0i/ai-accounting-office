"""성공 시 commit, 실패 시 rollback하며 항상 세션을 닫습니다."""

from types import TracebackType
from typing import Self

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.database.errors import map_database_error


class SQLAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._finished = False

    @property
    def session(self) -> Session:
        """Repository를 조립하는 infrastructure 경계에서만 사용합니다."""
        if self._session is None or self._finished:
            raise RuntimeError("활성화된 작업 범위 안에서만 세션을 사용할 수 있습니다.")
        return self._session

    def __enter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("작업 범위를 중첩해서 시작할 수 없습니다.")
        self._session = self._session_factory()
        self._finished = False
        try:
            self._session.begin()
        except SQLAlchemyError as error:
            self._session.close()
            self._session = None
            raise map_database_error(error) from None
        return self

    def commit(self) -> None:
        session = self.session
        try:
            session.commit()
        except SQLAlchemyError as error:
            self.rollback()
            raise map_database_error(error) from None
        except BaseException:
            self.rollback()
            raise
        finally:
            self._finished = True

    def rollback(self) -> None:
        session = self.session
        try:
            session.rollback()
        except SQLAlchemyError as error:
            raise map_database_error(error) from None
        finally:
            self._finished = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if not self._finished:
                if exc_type is None:
                    self.commit()
                else:
                    self.rollback()
                    if isinstance(exc, SQLAlchemyError):
                        raise map_database_error(exc) from None
        finally:
            if self._session is not None:
                try:
                    self._session.close()
                except SQLAlchemyError as error:
                    raise map_database_error(error) from None
                finally:
                    self._session = None
