"""Allow immutable cash flow snapshots in the existing report run lifecycle.

Revision ID: 029_cash_flow_report_export
Revises: 028_tax_preparation
"""

from collections.abc import Sequence

from alembic import op

revision: str = "029_cash_flow_report_export"
down_revision: str | Sequence[str] | None = "028_tax_preparation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"), "report_generation_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS','CASH_FLOW')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"), "report_generation_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS')",
    )
