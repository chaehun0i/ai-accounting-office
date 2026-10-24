"""Store report artifact metadata with company-scoped source linkage.

Revision ID: 023_report_artifacts
Revises: 022_report_generation_runs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "023_report_artifacts"
down_revision: str | Sequence[str] | None = "022_report_generation_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_generation_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("storage_object_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(180), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "id"),
        sa.UniqueConstraint("company_id", "run_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "run_id"],
            ["report_generation_runs.company_id", "report_generation_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "storage_object_id", "file_sha256"],
            ["storage_objects.company_id", "storage_objects.id", "storage_objects.sha256"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 2000000",
            name=op.f("ck_report_generation_artifacts_size"),
        ),
    )


def downgrade() -> None:
    op.drop_table("report_generation_artifacts")
