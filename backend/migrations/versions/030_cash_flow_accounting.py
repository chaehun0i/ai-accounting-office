"""Company-specific, append-only cash flow presentation policies."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "030_cash_flow_accounting"
down_revision: str | Sequence[str] | None = "029_cash_flow_report_export"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_cash_flow_adjustment_rules_adjustment_code"),
        "cash_flow_adjustment_rules",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_cash_flow_adjustment_rules_related_account"),
        "cash_flow_adjustment_rules",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_cash_flow_adjustment_rules_adjustment_code"),
        "cash_flow_adjustment_rules",
        "adjustment_code IN ('OPERATING_RESULT','NONCASH_PAIR',"
        "'WORKING_CAPITAL','EXCLUDED_BALANCE','DISPOSAL_GAIN')",
    )
    op.create_check_constraint(
        op.f("ck_cash_flow_adjustment_rules_related_account"),
        "cash_flow_adjustment_rules",
        "(adjustment_code IN ('NONCASH_PAIR','DISPOSAL_GAIN') "
        "AND related_account_id IS NOT NULL AND related_account_id <> account_id) OR "
        "(adjustment_code NOT IN ('NONCASH_PAIR','DISPOSAL_GAIN') "
        "AND related_account_id IS NULL)",
    )
    op.create_table(
        "cash_flow_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("interest_paid", sa.String(20), nullable=False),
        sa.Column("interest_received", sa.String(20), nullable=False),
        sa.Column("income_tax_paid", sa.String(20), nullable=False),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "id"),
        sa.UniqueConstraint("company_id", "version"),
        sa.UniqueConstraint("company_id", "effective_from"),
        sa.CheckConstraint("version >= 1", name=op.f("ck_cash_flow_policies_version_positive")),
        sa.CheckConstraint(
            "interest_paid IN ('OPERATING','FINANCING')",
            name=op.f("ck_cash_flow_policies_interest_paid"),
        ),
        sa.CheckConstraint(
            "interest_received IN ('OPERATING','INVESTING')",
            name=op.f("ck_cash_flow_policies_interest_received"),
        ),
        sa.CheckConstraint(
            "income_tax_paid IN ('OPERATING','INVESTING','FINANCING')",
            name=op.f("ck_cash_flow_policies_income_tax_paid"),
        ),
    )
    op.create_table(
        "cash_flow_non_cash_disclosures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("journal_id", sa.Uuid(), nullable=False),
        sa.Column("debit_line_id", sa.Uuid(), nullable=False),
        sa.Column("credit_line_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "id"),
        sa.UniqueConstraint("company_id", "journal_id", "debit_line_id", "credit_line_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id", "debit_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id", "credit_line_id"],
            ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "debit_line_id <> credit_line_id",
            name=op.f("ck_cash_flow_non_cash_disclosures_distinct_lines"),
        ),
        sa.CheckConstraint(
            "amount > 0 AND version >= 1",
            name=op.f("ck_cash_flow_non_cash_disclosures_amount_version"),
        ),
        sa.CheckConstraint(
            "source_type IN ('LEASE_IN_KIND','EQUITY_CONTRIBUTION_IN_KIND',"
            "'DEBT_EQUITY_CONVERSION','OTHER_VERIFIED')",
            name=op.f("ck_cash_flow_non_cash_disclosures_source_type"),
        ),
    )
    op.create_table(
        "cash_flow_statement_disclosures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("disclosure_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.UniqueConstraint("company_id", "id"),
        sa.UniqueConstraint("statement_id", "disclosure_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["cash_flow_statements.company_id", "cash_flow_statements.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "disclosure_id"],
            ["cash_flow_non_cash_disclosures.company_id", "cash_flow_non_cash_disclosures.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "amount > 0", name=op.f("ck_cash_flow_statement_disclosures_amount_positive")
        ),
    )
    op.create_table(
        "cash_flow_disposal_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("journal_id", sa.Uuid(), nullable=False),
        sa.Column("cash_line_id", sa.Uuid(), nullable=False),
        sa.Column("asset_line_id", sa.Uuid(), nullable=False),
        sa.Column("gain_line_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("proceeds", sa.Numeric(20, 4), nullable=False),
        sa.Column("gain_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "id"),
        sa.UniqueConstraint("company_id", "journal_id", "gain_line_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        *(
            sa.ForeignKeyConstraint(
                ["company_id", "journal_id", column],
                ["journal_lines.company_id", "journal_lines.journal_entry_id", "journal_lines.id"],
                ondelete="RESTRICT",
            )
            for column in ("cash_line_id", "asset_line_id", "gain_line_id")
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "proceeds > 0 AND gain_amount <> 0 AND version >= 1",
            name=op.f("ck_cash_flow_disposal_sources_amounts"),
        ),
        sa.CheckConstraint(
            "cash_line_id <> asset_line_id AND cash_line_id <> gain_line_id "
            "AND asset_line_id <> gain_line_id",
            name=op.f("ck_cash_flow_disposal_sources_distinct_lines"),
        ),
    )
    op.create_table(
        "cash_flow_statement_disposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("disposal_id", sa.Uuid(), nullable=False),
        sa.Column("proceeds", sa.Numeric(20, 4), nullable=False),
        sa.Column("gain_amount", sa.Numeric(20, 4), nullable=False),
        sa.UniqueConstraint("company_id", "id"),
        sa.UniqueConstraint("statement_id", "disposal_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["cash_flow_statements.company_id", "cash_flow_statements.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "disposal_id"],
            ["cash_flow_disposal_sources.company_id", "cash_flow_disposal_sources.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "proceeds > 0 AND gain_amount <> 0",
            name=op.f("ck_cash_flow_statement_disposals_amounts"),
        ),
    )
    for table in (
        "cash_flow_policies",
        "cash_flow_non_cash_disclosures",
        "cash_flow_statement_disclosures",
        "cash_flow_disposal_sources",
        "cash_flow_statement_disposals",
    ):
        op.execute(
            f"CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
        )


def downgrade() -> None:
    op.drop_table("cash_flow_statement_disposals")
    op.drop_table("cash_flow_disposal_sources")
    op.drop_table("cash_flow_statement_disclosures")
    op.drop_table("cash_flow_non_cash_disclosures")
    op.drop_table("cash_flow_policies")
    op.drop_constraint(
        op.f("ck_cash_flow_adjustment_rules_adjustment_code"),
        "cash_flow_adjustment_rules",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_cash_flow_adjustment_rules_related_account"),
        "cash_flow_adjustment_rules",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_cash_flow_adjustment_rules_adjustment_code"),
        "cash_flow_adjustment_rules",
        "adjustment_code IN ('OPERATING_RESULT','NONCASH_PAIR',"
        "'WORKING_CAPITAL','EXCLUDED_BALANCE')",
    )
    op.create_check_constraint(
        op.f("ck_cash_flow_adjustment_rules_related_account"),
        "cash_flow_adjustment_rules",
        "(adjustment_code = 'NONCASH_PAIR' AND related_account_id IS NOT NULL "
        "AND related_account_id <> account_id) OR "
        "(adjustment_code <> 'NONCASH_PAIR' AND related_account_id IS NULL)",
    )
