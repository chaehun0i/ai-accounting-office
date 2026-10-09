"""테스트 전용 PostgreSQL에만 연결합니다. 개발·운영 DB를 테스트에 재사용하지 않습니다."""

import os
from collections.abc import Iterator

import pytest
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, make_url, text

from app.core.config import Settings
from app.core.database.engine import create_database_engine


@pytest.fixture(scope="session")
def db_engine(pytestconfig: pytest.Config) -> Iterator[Engine]:
    raw_url = os.getenv("TEST_POSTGRES_URL")
    if not raw_url:
        if pytestconfig.getoption("--require-postgres"):
            pytest.fail("TEST_POSTGRES_URL에 테스트 전용 PostgreSQL 주소를 설정해 주세요.")
        pytest.skip("PostgreSQL 검증은 TEST_POSTGRES_URL 설정 후 실행하세요.")
    try:
        url = make_url(raw_url)
        assert url.get_backend_name() in {"postgres", "postgresql"}
        assert url.database and url.database.endswith("_test")
    except (ValueError, AssertionError):
        pytest.fail("테스트 DB는 PostgreSQL이며 이름이 _test로 끝나야 합니다.", pytrace=False)
    settings = Settings(
        _env_file=None,
        app_environment="test",
        postgres_url=SecretStr(raw_url),
        redis_url=SecretStr("redis://localhost:6379/0"),
    )
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_connection(db_engine: Engine) -> Iterator[Connection]:
    with db_engine.connect() as connection:
        connection.execute(text("CREATE TEMP TABLE foundation_probe (value INTEGER)"))
        connection.commit()
        try:
            yield connection
        finally:
            connection.rollback()
            # 물리 연결을 닫아 테스트에서 만든 모든 임시 테이블을 제거합니다.
            connection.invalidate()
