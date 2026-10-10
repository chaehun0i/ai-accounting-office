"""테스트 전용 PostgreSQL에만 연결합니다. 개발·운영 DB를 테스트에 재사용하지 않습니다."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, make_url, text
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker

from app.companies.infrastructure.seed import seed_permissions
from app.core.config import Settings
from app.core.database.engine import create_database_engine
from app.core.security import PasswordSecurity, TokenSecurity
from app.identity.auth.application.service import AuthService
from app.identity.infrastructure.unit_of_work import IdentitySQLAlchemyUnitOfWork


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
    except (ValueError, AssertionError, ArgumentError):
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


@pytest.fixture(scope="session")
def identity_database(db_engine: Engine) -> Engine:
    with db_engine.connect() as connection:
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return db_engine


@pytest.fixture
def auth_service(identity_database: Engine) -> Iterator[tuple[AuthService, Connection]]:
    with identity_database.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            autobegin=False,
            join_transaction_mode="create_savepoint",
        )
        with factory() as seed_session:
            seed_session.begin()
            seed_permissions(seed_session)
            seed_session.commit()
        service = AuthService(
            lambda: IdentitySQLAlchemyUnitOfWork(factory),
            PasswordSecurity(),
            TokenSecurity("test-only-signing-key-with-at-least-32-bytes"),
        )
        try:
            yield service, connection
        finally:
            transaction.rollback()


@pytest.fixture
def api_client(auth_service: tuple[AuthService, Connection], settings: Settings, tmp_path: Path):
    from fastapi.testclient import TestClient

    from app.accounting.application.service import AccountingMasterService
    from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
    from app.companies.application.service import CompanyService
    from app.companies.infrastructure.unit_of_work import CompanySQLAlchemyUnitOfWork
    from app.composition import Services
    from app.identity.invitations.application.service import InvitationService
    from app.identity.invitations.infrastructure.unit_of_work import InvitationSQLAlchemyUnitOfWork
    from app.intake.application.service import IntakeService
    from app.intake.infrastructure.parser import parse_file
    from app.intake.infrastructure.unit_of_work import IntakeSQLAlchemyUnitOfWork
    from app.main import create_app
    from app.master_data.application.service import MasterDataService
    from app.storage.infrastructure.local import LocalObjectStorage

    auth, connection = auth_service
    factory = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        autobegin=False,
        join_transaction_mode="create_savepoint",
    )
    from app.accounting.transactions.application.service import TransactionService
    from app.accounting.transactions.infrastructure.unit_of_work import (
        TransactionSQLAlchemyUnitOfWork,
    )
    from app.onboarding.application.merge import OnboardingImportService
    from app.onboarding.application.service import OnboardingService
    from app.onboarding.infrastructure.template import parse_onboarding
    from app.onboarding.infrastructure.unit_of_work import OnboardingSQLAlchemyUnitOfWork


    onboarding = OnboardingService(lambda: OnboardingSQLAlchemyUnitOfWork(factory))
    app = create_app(settings)
    app.state.services = Services(
        auth,
        CompanyService(lambda: CompanySQLAlchemyUnitOfWork(factory)),
        InvitationService(lambda: InvitationSQLAlchemyUnitOfWork(factory)),
        AccountingMasterService(lambda: MasterSQLAlchemyUnitOfWork(factory)),
        MasterDataService(lambda: MasterSQLAlchemyUnitOfWork(factory)),
        IntakeService(
            lambda: IntakeSQLAlchemyUnitOfWork(factory), LocalObjectStorage(tmp_path), parse_file
        ),
        onboarding,
        OnboardingImportService(
            onboarding,
            IntakeService(
                lambda: IntakeSQLAlchemyUnitOfWork(factory),
                LocalObjectStorage(tmp_path),
                parse_onboarding,
            ),
        ),
        TransactionService(lambda: TransactionSQLAlchemyUnitOfWork(factory)),
    )
    with TestClient(app, headers={"X-CSRF-Protection": "1"}) as client:
        yield client
