from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[2]


def test_baseline_has_one_named_head() -> None:
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert script.get_heads() == ["005_onboarding_data_exchange"]
    identity = script.get_revision("001_identity")
    company = script.get_revision("002_tenant_company_rbac")
    assert identity is not None and identity.down_revision == "db_foundation"
    assert company is not None and company.down_revision == "001_identity"
    baseline = script.get_revision("db_foundation")
    assert baseline is not None
    assert baseline.down_revision is None

    master = script.get_revision("003_master_accounting_settings")
    assert master is not None and master.down_revision == "002_tenant_company_rbac"

    intake = script.get_revision("004_storage_evidence_intake")
    assert intake is not None and intake.down_revision == "003_master_accounting_settings"
