"""Company COA change history.

Revision ID: 019_account_changes
Revises: 018_report_period_policy
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019_account_changes"
down_revision: str | Sequence[str] | None = "018_report_period_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("before_code", sa.String(20), nullable=False),
        sa.Column("after_code", sa.String(20), nullable=False),
        sa.Column("before_name", sa.String(200), nullable=False),
        sa.Column("after_name", sa.String(200), nullable=False),
        sa.Column("before_status", sa.String(16), nullable=False),
        sa.Column("after_status", sa.String(16), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("next_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "next_version = previous_version + 1", name=op.f("ck_account_changes_version_step")
        ),
    )
    op.create_index(
        "ix_account_changes_company_account", "account_changes", ["company_id", "account_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_account_changes_company_account", table_name="account_changes")
    op.drop_table("account_changes")
