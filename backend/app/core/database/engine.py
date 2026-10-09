"""명시적으로 호출할 때만 PostgreSQL 엔진을 구성합니다."""

from sqlalchemy import URL, Engine, create_engine, make_url

from app.core.config import Settings


def database_url(settings: Settings) -> URL:
    try:
        url = make_url(settings.postgres_url.get_secret_value())
        if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError
        return url.set(drivername="postgresql+psycopg")
    except ValueError:
        raise ValueError("PostgreSQL 연결 설정을 확인해 주세요.") from None


def create_database_engine(settings: Settings) -> Engine:
    # 엔진 생성은 연결하지 않습니다. 첫 사용 시 연결하며 SQL·매개변수 출력은 끕니다.
    return create_engine(
        database_url(settings),
        echo=False,
        echo_pool=False,
        hide_parameters=True,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c timezone=UTC"},
    )
