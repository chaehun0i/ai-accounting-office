"""Evidence-backed allocation of complex cash journal legs.

Revision ID: 025_cash_flow_allocations
Revises: 024_cash_flow_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "025_cash_flow_allocations"
down_revision: str | Sequence[str] | None = "024_cash_flow_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_journal_lines_company_id_journal_entry_id_id"),
        "journal_lines",
        ["company_id", "journal_entry_id", "id"],
    )
    op.create_table(
        "cash_flow_allocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("journal_id", sa.Uuid(), nullable=False),
        sa.Column("cash_line_id", sa.Uuid(), nullable=False),
        sa.Column("counterpart_line_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("replaces_id", sa.Uuid()),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "id"),
        sa.UniqueConstraint(
            "company_id", "journal_id", "cash_line_id", "counterpart_line_id", "version"
        ),
        sa.UniqueConstraint("company_id", "replaces_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id", "cash_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id", "counterpart_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "replaces_id"],
            ["cash_flow_allocations.company_id", "cash_flow_allocations.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_cash_flow_allocations_amount_nonnegative")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_cash_flow_allocations_version_positive")),
        sa.CheckConstraint(
            "cash_line_id <> counterpart_line_id",
            name=op.f("ck_cash_flow_allocations_distinct_lines"),
        ),
    )


def downgrade() -> None:
    op.drop_table("cash_flow_allocations")
    op.drop_constraint(
        op.f("uq_journal_lines_company_id_journal_entry_id_id"), "journal_lines", type_="unique"
    )
