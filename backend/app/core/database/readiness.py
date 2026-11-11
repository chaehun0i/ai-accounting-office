"""Read-only readiness checks: no credentials, SQL or schema versions in public results."""

from pathlib import Path
from typing import Literal

from alembic.script import ScriptDirectory
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError


class ReadinessRead(BaseModel):
    status: Literal["ready", "not_ready"]
    postgres: Literal["available", "unavailable"]
    migrations: Literal["current", "mismatch", "unavailable"]
    reason_code: Literal[
        "READY", "DATABASE_UNAVAILABLE", "MIGRATION_MISMATCH", "MIGRATION_UNAVAILABLE"
    ]
    llm: Literal["not_probed"] = "not_probed"
    redis: Literal["not_required"] = "not_required"


def migration_heads() -> tuple[str, ...]:
    directory = Path(__file__).resolve().parents[3] / "migrations"
    return tuple(sorted(ScriptDirectory(str(directory)).get_heads()))


class DatabaseReadiness:
    def __init__(self, engine: Engine, expected_heads: tuple[str, ...]) -> None:
        self.engine = engine
        self.expected_heads = tuple(sorted(expected_heads))

    def inspect(self) -> ReadinessRead:
        connected = False
        try:
            with self.engine.begin() as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                connected = connection.scalar(text("SELECT 1")) == 1
                actual = tuple(
                    sorted(
                        connection.scalars(text("SELECT version_num FROM public.alembic_version"))
                    )
                )
            if not connected:
                return ReadinessRead(
                    status="not_ready",
                    postgres="unavailable",
                    migrations="unavailable",
                    reason_code="DATABASE_UNAVAILABLE",
                )
            if not self.expected_heads or actual != self.expected_heads:
                return ReadinessRead(
                    status="not_ready",
                    postgres="available",
                    migrations="mismatch",
                    reason_code="MIGRATION_MISMATCH",
                )
            return ReadinessRead(
                status="ready", postgres="available", migrations="current", reason_code="READY"
            )
        except SQLAlchemyError:
            return ReadinessRead(
                status="not_ready",
                postgres="available" if connected else "unavailable",
                migrations="unavailable",
                reason_code="MIGRATION_UNAVAILABLE" if connected else "DATABASE_UNAVAILABLE",
            )
