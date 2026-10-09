import importlib
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import InvalidRequestError

from app.core.config import Settings
from app.core.database.engine import create_database_engine, database_url
from app.core.database.session import create_session_factory


def test_factory_does_not_connect_or_echo(settings: Settings) -> None:
    with patch("psycopg.connect", side_effect=AssertionError("연결하면 안 됩니다.")):
        engine = create_database_engine(settings)
        assert engine.echo is False
        assert engine.hide_parameters is True
        assert "placeholder" not in repr(engine)
        assert database_url(settings).drivername == "postgresql+psycopg"
        session = create_session_factory(engine)()
        with pytest.raises(InvalidRequestError):
            session.execute(text("SELECT 1"))
        session.close()
        engine.dispose()


def test_database_import_does_not_create_engine() -> None:
    with patch("sqlalchemy.create_engine", side_effect=AssertionError("엔진 생성 금지")):
        import app.core.database.engine as module

        importlib.reload(module)
    importlib.reload(module)
