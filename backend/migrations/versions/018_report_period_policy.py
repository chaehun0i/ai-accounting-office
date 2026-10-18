"""Company reporting week policy.

Revision ID: 018_report_period_policy
Revises: 017_accounting_agent_queries
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018_report_period_policy"
down_revision: str | Sequence[str] | None = "017_accounting_agent_queries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounting_settings",
        sa.Column("reporting_week_start", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        op.f("ck_accounting_settings_reporting_week_start"),
        "accounting_settings",
        "reporting_week_start BETWEEN 0 AND 6",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_accounting_settings_reporting_week_start"),
        "accounting_settings",
        type_="check",
    )
    op.drop_column("accounting_settings", "reporting_week_start")
