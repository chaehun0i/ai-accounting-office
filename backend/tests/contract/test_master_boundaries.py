"""회사 범위와 회계 명령의 정적 계약을 확인합니다."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "app"


def test_company_repositories_require_company_scope():
    for relative in (
        "master_data/payment_terms/infrastructure/repository.py",
        "master_data/counterparties/infrastructure/repository.py",
        "accounting/accounts/infrastructure/repository.py",
        "accounting/periods/infrastructure/repository.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        assert not any(node.name == "get_by_id" for node in methods)
        getter = next(node for node in methods if node.name == "get")
        assert [arg.arg for arg in getter.args.kwonlyargs] == ["company_id", "resource_id"]


def test_no_master_money_float_or_generic_columns():
    for root in (ROOT / "accounting", ROOT / "master_data"):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    assert node.id not in {"Float", "JSON", "JSONB"}, path
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    assert node.target.id not in {
                        "metadata",
                        "extra",
                        "payload",
                        "context",
                        "options",
                    }, path
