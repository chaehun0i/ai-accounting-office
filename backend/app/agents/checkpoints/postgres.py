"""공식 checkpointer를 격리된 스키마에서만 사용합니다."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row

SCHEMA = "agent_checkpoints"


class PostgresCheckpoints:
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    @contextmanager
    def open(self, thread_id: str) -> Iterator[PostgresSaver]:
        with psycopg.connect(
            self._connection_string,
            autocommit=True,
            row_factory=dict_row,
            prepare_threshold=0,
            options="-c search_path=agent_checkpoints",
        ) as connection:
            # 공식 migration은 동시 초기화를 막고 별도 schema 안에서만 수행합니다.
            connection.execute("SELECT pg_advisory_lock(82110626)")
            try:
                saver = PostgresSaver(connection)
                saver.setup()
            finally:
                connection.execute("SELECT pg_advisory_unlock(82110626)")
            connection.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", (thread_id,))
            try:
                yield saver
            finally:
                connection.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s,0))", (thread_id,)
                )
