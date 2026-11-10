"""Round-trip a test-only PostgreSQL backup without touching the development database.

Run with backend/.venv/Scripts/python.exe scripts/verify_postgres_recovery.py.
Archives/reports remain under ignored .local/release-gate; restored DB is retained.
"""

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


def docker(*args: str) -> str:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=180, check=False
    )
    if result.returncode:
        raise RuntimeError(
            "Docker recovery command failed; inspect the container locally"
        )
    return result.stdout


def fingerprint(url: URL) -> dict[str, object]:
    engine = create_engine(url)
    result: dict[str, object] = {}
    try:
        with engine.connect() as connection:
            tables = connection.execute(
                text(
                    "SELECT schemaname, tablename FROM pg_tables "
                    "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
                    "ORDER BY schemaname, tablename"
                )
            ).all()
            quote = engine.dialect.identifier_preparer.quote
            for schema, table in tables:
                rows = connection.execute(
                    text(
                        f"SELECT row_to_json(t)::text FROM {quote(schema)}.{quote(table)} t "
                        "ORDER BY row_to_json(t)::text"
                    )
                ).scalars()
                checksum = hashlib.sha256()
                count = 0
                for row in rows:
                    checksum.update(row.encode())
                    checksum.update(b"\n")
                    count += 1
                result[f"{schema}.{table}"] = {
                    "rows": count,
                    "sha256": checksum.hexdigest(),
                }
    finally:
        engine.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="ai-accounting-office-postgres-1")
    parser.add_argument("--database", default="agent_workflow_test")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]*_test", args.database):
        parser.error("Only an explicitly named *_test database is allowed")
    info = json.loads(docker("inspect", args.container))[0]
    values = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    if args.database == values.get("POSTGRES_DB"):
        parser.error("The container's configured development database cannot be used")
    bindings = info["NetworkSettings"]["Ports"]["5432/tcp"]
    binding = next(
        item for item in bindings if item["HostIp"] in ("127.0.0.1", "0.0.0.0")
    )
    url = URL.create(
        "postgresql+psycopg",
        username=values["POSTGRES_USER"],
        password=values["POSTGRES_PASSWORD"],
        host="127.0.0.1",
        port=int(binding["HostPort"]),
        database=args.database,
        query={"connect_timeout": "5"},
    )
    identity = uuid4().hex[:12]
    restored = f"recovery_{identity}_test"
    archive = f"/tmp/recovery_{identity}.dump"
    output = Path(__file__).resolve().parents[1] / ".local" / "release-gate" / identity
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    before = fingerprint(url)
    docker(
        "exec",
        args.container,
        "pg_dump",
        "-U",
        values["POSTGRES_USER"],
        "-d",
        args.database,
        "-Fc",
        "-f",
        archive,
    )
    docker("cp", f"{args.container}:{archive}", str(output / "database.dump"))
    docker("exec", args.container, "createdb", "-U", values["POSTGRES_USER"], restored)
    docker(
        "exec",
        args.container,
        "pg_restore",
        "-U",
        values["POSTGRES_USER"],
        "--exit-on-error",
        "-d",
        restored,
        archive,
    )
    after = fingerprint(url.set(database=restored))
    source_stable = before == fingerprint(url)
    report = {
        "source_database": args.database,
        "restored_database": restored,
        "tables": len(before),
        "source_stable": source_stable,
        "rows_and_digests_match": before == after,
        "archive_sha256": hashlib.sha256(
            (output / "database.dump").read_bytes()
        ).hexdigest(),
        "duration_seconds": round(time.monotonic() - started, 2),
        "scope": "TEST_DATABASE_ONLY",
        "artifact_storage_verified": False,
    }
    (output / "recovery-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if not source_stable or before != after:
        raise SystemExit(
            "Recovery mismatch: report retained; no databases were deleted"
        )


if __name__ == "__main__":
    main()
