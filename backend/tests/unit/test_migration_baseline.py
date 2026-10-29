from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[2]


def test_baseline_has_one_named_head() -> None:
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert script.get_heads() == ["030_cash_flow_accounting"]
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

    previous = "005_onboarding_data_exchange"
    for name in (
        "006_transactions",
        "007_journal_core",
        "008_governance",
        "009_finance_subledger",
        "010_agent_runtime_foundation",
        "011_accounting_dimensions",
        "012_import_transaction_promotion",
        "013_business_documents",
        "014_bank_card_reconciliation",
        "015_period_closing",
        "016_financial_statements",
        "017_accounting_agent_queries",
        "018_report_period_policy",
        "019_account_changes",
        "020_control_account_roles",
        "021_opening_ar_ap_promotion",
        "022_report_generation_runs",
        "023_report_artifacts",
        "024_cash_flow_foundation",
        "025_cash_flow_allocations",
        "026_cash_flow_indirect",
        "027_cash_flow_snapshots",
        "028_tax_preparation",
        "029_cash_flow_report_export",
        "030_cash_flow_accounting",
    ):
        revision = script.get_revision(name)
        assert revision is not None and revision.down_revision == previous
        previous = name
