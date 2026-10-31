"""Add SCE to the existing Report Center catalog constraint."""

from collections.abc import Sequence

from alembic import op

revision: str = "032_equity_report_export"
down_revision: str | Sequence[str] | None = "031_equity_statement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT',"
        "'FINANCIAL_METRICS','CASH_FLOW','CHANGES_IN_EQUITY')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS','CASH_FLOW')",
    )
