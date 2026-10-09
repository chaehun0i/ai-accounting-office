"""Static dependency guard; dynamic imports are forbidden in agents/llm."""

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
            if not (name == "app.tools" or name.startswith("app.tools.")) and (
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
            package = ".".join(path.relative_to(APP.parent).parts[:-1])
            assert not forbidden_imports(path.read_text(encoding="utf-8"), package), path


@pytest.mark.parametrize(
    "source",
    [
        "from app.accounting.infrastructure import repository",
        "from app.tax.infrastructure.repository import TaxRepository",
        "from sqlalchemy.orm import Session",
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
