"""개발 데이터를 건드리지 않는 브라우저 검증 전용 API입니다."""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import uvicorn
from alembic import command
from alembic.config import Config
from app.accounting.templates.infrastructure.seed import seed_default_coa
from app.companies.infrastructure.seed import seed_permissions
from app.core.config import Settings
from app.main import create_app
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main() -> None:
    url = make_url(os.environ["TEST_POSTGRES_URL"]).set(drivername="postgresql+psycopg")
    name = url.database or ""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,50}_test", name):
        raise ValueError("브라우저 전용 DB 이름은 _test로 끝나야 합니다.")
    if url.host not in {"localhost", "127.0.0.1"}:
        raise ValueError("로컬 PostgreSQL만 사용할 수 있습니다.")
    admin = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", hide_parameters=True
    )
    created = False
    try:
        with admin.connect() as connection:
            if connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name}
            ):
                raise ValueError("이미 있는 DB는 사용하거나 덮어쓰지 않습니다.")
            # 위 정규식으로 식별자를 제한한 뒤 새 테스트 DB만 생성합니다.
            connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        engine = create_engine(url, hide_parameters=True)
        try:
            with engine.connect() as connection:
                config = Config(
                    str(Path(__file__).resolve().parents[1] / "backend/alembic.ini")
                )
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            with Session(engine) as session:
                seed_permissions(session)
                seed_default_coa(session)
                session.commit()
        finally:
            engine.dispose()
        settings = Settings(
            _env_file=None,
            app_environment="test",
            postgres_url=SecretStr(url.render_as_string(hide_password=False)),
            redis_url=SecretStr("redis://localhost:6379/0"),
            auth_signing_key=SecretStr(
                "browser-test-only-signing-key-at-least-32-bytes"
            ),
            frontend_origin=os.getenv(
                "ACCOUNTING_BROWSER_ORIGIN", "http://localhost:3000"
            ),
        )
        uvicorn.run(create_app(settings), host="127.0.0.1", port=8002, access_log=False)
    finally:
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
