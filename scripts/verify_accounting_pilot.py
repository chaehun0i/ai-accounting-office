"""Reproducible synthetic accounting release checks on an isolated test database.

This is not a real-customer shadow-accounting sign-off. Existing tests own
transactions and remain unchanged; no expected values or assertions are relaxed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "test_readiness.py",
    "test_journal_flow.py",
    "test_posting_concurrency.py",
    "test_closing_workflow.py",
    "test_equity_statement.py",
    "test_disclosures.py",
    "test_comparative_statements.py",
    "test_agent_reporting_tools.py",
    "test_report_center.py",
    "test_migrations.py",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="ai-accounting-office-postgres-1")
    parser.add_argument("--database", default="accounting_pilot_test")
    parser.add_argument("--test-file", action="append", choices=TESTS)
    args = parser.parse_args()
    selected_tests = args.test_file or TESTS
    if not re.fullmatch(r"[a-z][a-z0-9_]*_test", args.database):
        parser.error("Only *_test databases are allowed")
    info = json.loads(
        subprocess.check_output(
            ["docker", "inspect", args.container], text=True, timeout=15
        )
    )[0]
    values = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    if args.database == values.get("POSTGRES_DB"):
        parser.error("The configured development database cannot be used")
    bindings = info["NetworkSettings"]["Ports"]["5432/tcp"]
    port = next(
        item["HostPort"]
        for item in bindings
        if item["HostIp"] in ("127.0.0.1", "0.0.0.0")
    )
    url = URL.create(
        "postgresql+psycopg",
        username=values["POSTGRES_USER"],
        password=values["POSTGRES_PASSWORD"],
        host="127.0.0.1",
        port=int(port),
        database=values["POSTGRES_DB"],
        query={"connect_timeout": "5"},
    )
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        if not connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname=:name"),
            {"name": args.database},
        ):
            quote = engine.dialect.identifier_preparer.quote
            connection.execute(text(f"CREATE DATABASE {quote(args.database)}"))
    engine.dispose()
    environment = dict(os.environ)
    environment["TEST_POSTGRES_URL"] = url.set(database=args.database).render_as_string(
        hide_password=False
    )
    output = ROOT / ".local" / "release-gate" / ("pilot_" + uuid4().hex[:12])
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    command = [
        sys.executable,
        "-m",
        "pytest",
        *["tests/integration/" + name for name in selected_tests],
        "--require-postgres",
        "-q",
        "--junitxml=" + str(output / "pilot-tests.xml"),
    ]
    completed = subprocess.run(
        command, cwd=ROOT / "backend", env=environment, check=False
    )
    report = {
        "synthetic": True,
        "real_customer_signoff": False,
        "database": args.database,
        "test_files": list(selected_tests),
        "exit_code": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 2),
    }
    (output / "pilot-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
