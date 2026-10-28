"""Explicit indirect operating adjustment rules.

Revision ID: 026_cash_flow_indirect
Revises: 025_cash_flow_allocations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "026_cash_flow_indirect"
down_revision: str | Sequence[str] | None = "025_cash_flow_allocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cash_flow_adjustment_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("adjustment_code", sa.String(30), nullable=False),
        sa.Column("source_mapping_type", sa.String(30), nullable=False),
        sa.Column("related_account_id", sa.Uuid()),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("policy_code", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "id"),
        sa.UniqueConstraint("company_id", "account_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "related_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "version >= 1 AND policy_version >= 1",
            name=op.f("ck_cash_flow_adjustment_rules_versions"),
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_cash_flow_adjustment_rules_dates"),
        ),
        sa.CheckConstraint(
            "adjustment_code IN ('OPERATING_RESULT','NONCASH_PAIR',"
            "'WORKING_CAPITAL','EXCLUDED_BALANCE')",
            name=op.f("ck_cash_flow_adjustment_rules_adjustment_code"),
        ),
        sa.CheckConstraint(
            "source_mapping_type IN ('ACCOUNT_LEDGER','ASSET_REGISTER','INVENTORY_SUBLEDGER')",
            name=op.f("ck_cash_flow_adjustment_rules_source_mapping_type"),
        ),
        sa.CheckConstraint(
            "(adjustment_code = 'NONCASH_PAIR' AND related_account_id IS NOT NULL "
            "AND related_account_id <> account_id) OR "
            "(adjustment_code <> 'NONCASH_PAIR' AND related_account_id IS NULL)",
            name=op.f("ck_cash_flow_adjustment_rules_related_account"),
        ),
    )


def downgrade() -> None:
    op.drop_table("cash_flow_adjustment_rules")
