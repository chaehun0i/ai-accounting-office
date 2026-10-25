"""Track immutable report source and generation state.

Revision ID: 022_report_generation_runs
Revises: 021_opening_ar_ap_promotion
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022_report_generation_runs"
down_revision: str | Sequence[str] | None = "021_opening_ar_ap_promotion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_generation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("report_code", sa.String(32), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("period_preset", sa.String(16), nullable=False),
        sa.Column("period_mode", sa.String(8), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("statement_set_id", sa.Uuid(), nullable=False),
        sa.Column("close_version", sa.Integer(), nullable=False),
        sa.Column("taxonomy_version", sa.Integer(), nullable=False),
        sa.Column("trial_balance_digest", sa.String(64), nullable=False),
        sa.Column("mapping_digest", sa.String(64), nullable=False),
        sa.Column("balance_sheet_digest", sa.String(64), nullable=False),
        sa.Column("income_statement_digest", sa.String(64), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "requested_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(48)),
        sa.Column("retry_of_run_id", sa.Uuid()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("company_id", "id"),
        sa.UniqueConstraint("company_id", "requested_by", "idempotency_key"),
        sa.ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "retry_of_run_id"],
            ["report_generation_runs.company_id", "report_generation_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS')",
            name=op.f("ck_report_generation_runs_report_code"),
        ),
        sa.CheckConstraint(
            "format IN ('PDF','XLSX','CSV')", name=op.f("ck_report_generation_runs_format")
        ),
        sa.CheckConstraint(
            "period_mode IN ('AS_OF','RANGE')", name=op.f("ck_report_generation_runs_period_mode")
        ),
        sa.CheckConstraint(
            "(period_mode = 'AS_OF' AND as_of IS NOT NULL AND date_from IS NULL "
            "AND date_to IS NULL) OR (period_mode = 'RANGE' AND as_of IS NULL "
            "AND date_from IS NOT NULL AND date_to IS NOT NULL "
            "AND date_from <= date_to)",
            name=op.f("ck_report_generation_runs_period_dates"),
        ),
        sa.CheckConstraint(
            "status IN ('REQUESTED','GENERATING','COMPLETED','FAILED')",
            name=op.f("ck_report_generation_runs_status"),
        ),
        sa.CheckConstraint(
            "close_version >= 1 AND taxonomy_version >= 1 "
            "AND template_version >= 1 AND version >= 1",
            name=op.f("ck_report_generation_runs_version"),
        ),
    )
    op.create_index(
        "ix_report_generation_runs_company_requested",
        "report_generation_runs",
        ["company_id", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_report_generation_runs_company_requested", table_name="report_generation_runs"
    )
    op.drop_table("report_generation_runs")
