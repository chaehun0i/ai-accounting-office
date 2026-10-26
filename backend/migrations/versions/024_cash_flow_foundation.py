"""Add explicit company cash scope and counterpart activity mappings.

Revision ID: 024_cash_flow_foundation
Revises: 023_report_artifacts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "024_cash_flow_foundation"
down_revision: str | Sequence[str] | None = "023_report_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def mapping_columns(table: str) -> list:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("status", sa.String(12), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name=op.f(f"ck_{table}_status")),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name=op.f(f"ck_{table}_dates")
        ),
        sa.CheckConstraint("version >= 1", name=op.f(f"ck_{table}_version")),
    ]


def upgrade() -> None:
    scope = mapping_columns("cash_scope_mappings")
    scope.insert(3, sa.Column("scope_type", sa.String(20), nullable=False))
    scope.append(
        sa.CheckConstraint(
            "scope_type IN ('CASH','CASH_EQUIVALENT')",
            name=op.f("ck_cash_scope_mappings_scope_type"),
        )
    )
    op.create_table("cash_scope_mappings", *scope)

    classifications = mapping_columns("cash_flow_classifications")
    classifications.insert(3, sa.Column("activity_type", sa.String(20), nullable=False))
    classifications.insert(4, sa.Column("line_code", sa.String(40), nullable=False))
    classifications.append(
        sa.CheckConstraint(
            "activity_type IN ('OPERATING','INVESTING','FINANCING','EXCHANGE_EFFECT')",
            name=op.f("ck_cash_flow_classifications_activity_type"),
        )
    )
    op.create_table("cash_flow_classifications", *classifications)


def downgrade() -> None:
    op.drop_table("cash_flow_classifications")
    op.drop_table("cash_scope_mappings")
