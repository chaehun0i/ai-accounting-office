"""애플리케이션 서버를 시작하지 않고 메타데이터와 연결 설정만 사용합니다."""

from alembic import context
from alembic.util import CommandError
from sqlalchemy import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import load_settings
from app.core.database.base import Base
from app.core.database.engine import create_database_engine
from app.core.database.errors import map_database_error

config = context.config


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    # 오프라인 SQL 생성에는 접속 주소나 실행 환경의 비밀값이 필요하지 않습니다.
    context.configure(
        dialect_name="postgresql",
        target_metadata=Base.metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    try:
        connection = config.attributes.get("connection")
        if isinstance(connection, Connection):
            run_migrations(connection)
        else:
            engine = create_database_engine(load_settings())
            try:
                with engine.connect() as connection:
                    run_migrations(connection)
            finally:
                engine.dispose()
    except SQLAlchemyError as error:
        raise CommandError(map_database_error(error).message) from None
