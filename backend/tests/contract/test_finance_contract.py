"""재무 API는 명령별 계약과 회사 범위 Repository를 유지합니다."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.finance.settlements.api.schemas import Allocate, Confirm, SettlementCreate
from app.main import create_app


def test_finance_openapi_contract(settings):
    schema = create_app(settings).openapi()
    for targets, headers in [("receivables", "collections"), ("payables", "payments")]:
        for path in [
            f"/{targets}",
            f"/{targets}/{{resource_id}}",
            f"/{targets}/aging",
            f"/{targets}/reconciliation",
            f"/{headers}",
            f"/{headers}/{{resource_id}}",
        ]:
            assert "get" in schema["paths"][path]
        for path in [
            f"/{headers}",
            f"/{headers}/{{resource_id}}/allocations",
            f"/{headers}/{{resource_id}}/confirm",
        ]:
            operation = schema["paths"][path]["post"]
            assert any(
                param["name"] == "Idempotency-Key" and param["required"]
                for param in operation["parameters"]
            )
            assert any(
                param["name"] == "X-Company-ID" and param["required"]
                for param in operation["parameters"]
            )
    for model in (Allocate, Confirm, SettlementCreate):
        assert model.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        Confirm(expected_version=1, status="CONFIRMED")


def test_finance_company_scope_and_no_generic_money():
    root = Path(__file__).parents[2] / "app/finance"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in {"Float", "JSON", "JSONB"}, path
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "float", path
            if isinstance(node, ast.FunctionDef) and node.name == "get":
                assert "company_id" in [arg.arg for arg in node.args.args]
            if isinstance(node, ast.FunctionDef):
                assert node.name != "get_by_id", path
