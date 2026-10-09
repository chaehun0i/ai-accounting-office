from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[2]


def test_baseline_has_one_named_head() -> None:
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert script.get_heads() == ["002_tenant_company_rbac"]
    identity = script.get_revision("001_identity")
    company = script.get_revision("002_tenant_company_rbac")
    assert identity is not None and identity.down_revision == "db_foundation"
    assert company is not None and company.down_revision == "001_identity"
    baseline = script.get_revision("db_foundation")
    assert baseline is not None
    assert baseline.down_revision is None
