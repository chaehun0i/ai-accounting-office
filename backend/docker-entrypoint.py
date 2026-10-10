"""로컬 Compose에서만 마이그레이션·기본 seed 후 API를 실행합니다."""

import os
from urllib.parse import urlsplit, urlunsplit

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.accounting.templates.infrastructure.seed import main as seed_templates
from app.companies.infrastructure.seed import main as seed_permissions
from app.core.config import load_settings
from app.main import create_app


def main() -> None:
    if os.environ.get("APP_ENVIRONMENT") != "local":
        raise RuntimeError("이 실행 명령은 로컬 개발용입니다.")
    # 호스트 접속용 URL의 자격 증명은 유지하고 Compose 내부 주소만 변경합니다.
    address = make_url(os.environ["POSTGRES_URL"]).set(host="postgres", port=5432)
    os.environ["POSTGRES_URL"] = address.render_as_string(hide_password=False)
    redis = urlsplit(os.environ["REDIS_URL"])
    os.environ["REDIS_URL"] = urlunsplit((redis.scheme, "redis:6379", redis.path, "", ""))
    command.upgrade(Config("alembic.ini"), "head")
    seed_permissions()
    seed_templates()
    uvicorn.run(create_app(load_settings()), host="0.0.0.0", port=8000, access_log=False)


if __name__ == "__main__":
    main()
