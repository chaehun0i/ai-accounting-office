"""Link opening open items to their import without inventing journal lines.

Revision ID: 021_opening_ar_ap_promotion
Revises: 020_control_account_roles
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021_opening_ar_ap_promotion"
down_revision: str | Sequence[str] | None = "020_control_account_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("opening_balance_imports", sa.Column("ar_ap_digest", sa.String(64)))
    op.add_column(
        "opening_balance_imports", sa.Column("ar_ap_promoted_at", sa.DateTime(timezone=True))
    )
    for table in ("receivables", "payables"):
        op.add_column(table, sa.Column("opening_balance_import_id", sa.Uuid()))
        op.add_column(table, sa.Column("opening_source_row_key", sa.String(300)))
        op.add_column(table, sa.Column("opening_reference_code", sa.String(100)))
        op.create_index(
            f"ix_{table}_opening_balance_import_id", table, ["opening_balance_import_id"]
        )
        op.create_unique_constraint(
            f"uq_{table}_opening_source",
            table,
            ["company_id", "opening_balance_import_id", "opening_source_row_key"],
        )
        op.create_foreign_key(
            f"fk_{table}_opening_import",
            table,
            "opening_balance_imports",
            ["company_id", "opening_balance_import_id"],
            ["company_id", "id"],
            ondelete="RESTRICT",
        )
        op.drop_constraint(op.f(f"ck_{table}_source"), table, type_="check")
        op.create_check_constraint(
            op.f(f"ck_{table}_source"),
            table,
            "(origin_journal_id IS NOT NULL AND origin_line_no IS NOT NULL) OR "
            "(source_invoice_id IS NOT NULL AND source_transaction_id IS NOT NULL "
            "AND recognized_date IS NOT NULL) OR "
            "(opening_balance_import_id IS NOT NULL AND opening_source_row_key IS NOT NULL "
            "AND opening_reference_code IS NOT NULL AND origin_journal_id IS NOT NULL "
            "AND origin_line_no IS NULL AND recognized_date IS NOT NULL)",
        )


def downgrade() -> None:
    for table in ("payables", "receivables"):
        op.drop_constraint(op.f(f"ck_{table}_source"), table, type_="check")
        op.create_check_constraint(
            op.f(f"ck_{table}_source"),
            table,
            "(origin_journal_id IS NOT NULL AND origin_line_no IS NOT NULL) OR "
            "(source_invoice_id IS NOT NULL AND source_transaction_id IS NOT NULL "
            "AND recognized_date IS NOT NULL)",
        )
        op.drop_constraint(
            f"fk_{table}_opening_import",
            table,
            type_="foreignkey",
        )
        op.drop_constraint(
            f"uq_{table}_opening_source",
            table,
            type_="unique",
        )
        op.drop_index(f"ix_{table}_opening_balance_import_id", table_name=table)
        for column in (
            "opening_reference_code",
            "opening_source_row_key",
            "opening_balance_import_id",
        ):
            op.drop_column(table, column)
    op.drop_column("opening_balance_imports", "ar_ap_promoted_at")
    op.drop_column("opening_balance_imports", "ar_ap_digest")
