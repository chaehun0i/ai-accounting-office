"""Agent/LLM의 정적 의존성 경계를 검사하며 동적 import를 금지합니다."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"


def forbidden_imports(source: str, package: str) -> list[str]:
    violations = []
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                module = ".".join([*base, module]).rstrip(".")
            names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"__import__", "eval", "exec"}:
                violations.append(node.func.id)
        for name in names:
            allowed = (
                "app.tools",
                "app.llm",
                "app.agents",
                "app.jobs.application",
                "app.jobs.domain",
                "app.contracts",
                "app.core.digests",
                "app.identity.users.domain",
            )
            if not any(name == p or name.startswith(p + ".") for p in allowed) and (
                name == "app" or name.startswith("app.")
            ):
                violations.append(name)
            if name.split(".")[0] in {
                "sqlalchemy",
                "psycopg",
                "psycopg2",
                "asyncpg",
                "sqlite3",
                "importlib",
            }:
                violations.append(name)
    return violations


def test_agent_and_llm_boundaries() -> None:
    for root in (APP / "agents", APP / "llm"):
        for path in root.rglob("*.py"):
            # API는 인증/조립 경계, checkpoint는 framework 전용 연결 경계입니다.
            if "api" in path.parts or "checkpoints" in path.parts:
                continue
            package = ".".join(path.relative_to(APP.parent).parts[:-1])
            assert not forbidden_imports(path.read_text(encoding="utf-8"), package), path


@pytest.mark.parametrize(
    "source",
    [
        "from app.accounting.infrastructure import repository",
        "from app.tax.infrastructure.repository import TaxRepository",
        "from sqlalchemy.orm import Session",
        "from app.core.database import session",
        "from app.core.database.base import Base",
        "from app.core.database.unit_of_work import SQLAlchemyUnitOfWork",
        "from ..accounting import infrastructure",
        "from app import accounting",
        "import importlib",
        "__import__('sqlalchemy')",
    ],
)
def test_guard_rejects_bypass(source: str) -> None:
    assert forbidden_imports(source, "app.agents")


def test_guard_accepts_tools() -> None:
    assert not forbidden_imports("from app.tools import adapter", "app.agents")


def persistence_boundary_violations(source: str, package: str) -> list[str]:
    violations = []
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                module = ".".join([*base, module]).rstrip(".")
            names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
        for name in names:
            if (
                name.split(".")[0] in {"sqlalchemy", "fastapi", "psycopg", "asyncpg", "sqlite3"}
                or name.startswith("app.core.database")
                or "infrastructure" in name.split(".")
            ):
                violations.append(name)
    return violations


def test_domain_application_and_contracts_are_framework_free() -> None:
    for path in APP.rglob("*.py"):
        parts = path.relative_to(APP).parts
        if "domain" in parts or "application" in parts or parts[0] == "contracts":
            package = ".".join(path.relative_to(APP.parent).parts[:-1])
            assert not persistence_boundary_violations(path.read_text(encoding="utf-8"), package), (
                path
            )


@pytest.mark.parametrize(
    "source",
    [
        "from sqlalchemy.orm import Mapped",
        "import fastapi",
        "from app.core.database.session import create_session_factory",
        "from ..infrastructure.repository import Repository",
    ],
)
def test_domain_guard_rejects_frameworks(source: str) -> None:
    assert persistence_boundary_violations(source, "app.accounting.domain")


def test_domain_guard_accepts_pure_values_and_contracts() -> None:
    assert not persistence_boundary_violations(
        "from app.core.values import require_money\n"
        "from app.contracts.unit_of_work import UnitOfWork",
        "app.accounting.application",
    )


def repository_transaction_calls(source: str) -> list[str]:
    return [
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback", "begin", "begin_nested"}
    ]


def test_repositories_do_not_own_transactions() -> None:
    for path in APP.rglob("*.py"):
        if "repository" in path.stem or "repositories" in path.parts:
            assert not repository_transaction_calls(path.read_text(encoding="utf-8")), path


@pytest.mark.parametrize("method", ["commit", "rollback", "begin", "begin_nested"])
def test_repository_guard_rejects_transaction_ownership(method: str) -> None:
    assert repository_transaction_calls(f"session.{method}()")


def test_runtime_sdk_boundaries() -> None:
    allowed = {
        "google": ("llm/providers/",),
        "langgraph": ("agents/graphs/", "agents/runtime/", "agents/checkpoints/"),
        "langchain_core": ("tools/adapters/langchain.py", "agents/runtime/"),
        "mcp": ("tools/adapters/mcp",),
    }
    for path in APP.rglob("*.py"):
        relative = path.relative_to(APP).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for name in names:
                root = name.split(".")[0]
                if root in allowed:
                    assert any(relative.startswith(p) for p in allowed[root]), (relative, name)


def test_graph_cannot_execute_privileged_commands() -> None:
    for path in (APP / "agents" / "graphs").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("journal.post", "period.close", "payment.execute", "tax.filing.submit"):
            assert forbidden not in source


def test_tool_adapters_use_application_services_only() -> None:
    for path in (APP / "tools").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for name in names:
                assert name.split(".")[0] not in {"sqlalchemy", "psycopg", "asyncpg", "sqlite3"}
                assert "infrastructure" not in name.split(".")
