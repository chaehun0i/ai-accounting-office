"""Add comparative statement snapshots and reviewable presentation reclassification."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from app.core.database.types import MoneyNumeric

revision: str = "034_statement_comparatives"
down_revision: str | Sequence[str] | None = "033_disclosure_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comparative_statement_snapshots",
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("comparison_period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("statement_set_id", UUID(as_uuid=True), nullable=False),
        sa.Column("comparison_statement_set_id", UUID(as_uuid=True), nullable=False),
        sa.Column("close_version", sa.Integer(), nullable=False),
        sa.Column("comparison_close_version", sa.Integer(), nullable=False),
        sa.Column("current_source_digest", sa.String(64), nullable=False),
        sa.Column("comparison_source_digest", sa.String(64), nullable=False),
        sa.Column("current_mapping_digest", sa.String(64), nullable=False),
        sa.Column("comparison_mapping_digest", sa.String(64), nullable=False),
        sa.Column("taxonomy_version", sa.Integer(), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("review_digest", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comparative_statement_snapshots")),
        sa.UniqueConstraint(
            "company_id", "id", name=op.f("uq_comparative_statement_snapshots_company_id_id")
        ),
        sa.UniqueConstraint(
            "company_id",
            "period_id",
            "comparison_period_id",
            "source_digest",
            "revision",
            name="uq_comparative_statement_sources",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "comparison_period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "comparison_statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "period_id <> comparison_period_id",
            name="ck_comparative_statement_snapshots_different_periods",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','REVIEW_REQUESTED','APPROVED','REJECTED','SUPERSEDED')",
            name="ck_comparative_statement_snapshots_status",
        ),
        sa.CheckConstraint(
            "close_version > 0 AND comparison_close_version > 0",
            name="ck_comparative_statement_snapshots_close_version",
        ),
        sa.CheckConstraint(
            "taxonomy_version > 0 AND version > 0",
            name="ck_comparative_statement_snapshots_version",
        ),
        sa.CheckConstraint(
            "(status = 'APPROVED' AND reviewer_id IS NOT NULL AND approved_at IS NOT NULL "
            "AND review_digest IS NOT NULL) OR (status <> 'APPROVED' AND approved_at IS NULL)",
            name="ck_comparative_statement_snapshots_approval_fields",
        ),
    )
    op.create_index(
        "ix_comparative_statements_company_period",
        "comparative_statement_snapshots",
        ["company_id", "period_id"],
    )
    op.add_column(
        "financial_statement_snapshots",
        sa.Column("comparative_statement_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_financial_statement_snapshots_comparative_statement",
        "financial_statement_snapshots",
        "comparative_statement_snapshots",
        ["company_id", "comparative_statement_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.add_column("financial_statement_lines", sa.Column("prior_amount", MoneyNumeric()))
    op.add_column("financial_statement_lines", sa.Column("presentation_amount", MoneyNumeric()))
    op.add_column(
        "financial_statement_lines", sa.Column("current_source_line_id", UUID(as_uuid=True))
    )
    op.add_column(
        "financial_statement_lines", sa.Column("prior_source_line_id", UUID(as_uuid=True))
    )
    op.create_foreign_key(
        "fk_financial_statement_lines_current_source_line",
        "financial_statement_lines",
        "financial_statement_lines",
        ["company_id", "current_source_line_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_financial_statement_lines_prior_source_line",
        "financial_statement_lines",
        "financial_statement_lines",
        ["company_id", "prior_source_line_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_financial_statement_lines_comparative_amounts",
        "financial_statement_lines",
        "(prior_amount IS NULL AND presentation_amount IS NULL AND "
        "current_source_line_id IS NULL AND prior_source_line_id IS NULL) OR "
        "(prior_amount IS NOT NULL AND presentation_amount IS NOT NULL AND "
        "current_source_line_id IS NOT NULL AND prior_source_line_id IS NOT NULL)",
    )
    op.create_table(
        "comparative_reclassifications",
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("comparative_statement_id", UUID(as_uuid=True), nullable=False),
        sa.Column("statement_type", sa.String(24), nullable=False),
        sa.Column("from_line_code", sa.String(40), nullable=False),
        sa.Column("to_line_code", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(28, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comparative_reclassifications")),
        sa.UniqueConstraint(
            "company_id", "id", name=op.f("uq_comparative_reclassifications_company_id_id")
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "comparative_statement_id"],
            ["comparative_statement_snapshots.company_id", "comparative_statement_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_comparative_reclassifications_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "statement_type IN ('BALANCE_SHEET','INCOME_STATEMENT')",
            name="ck_comparative_reclassifications_statement_type",
        ),
        sa.CheckConstraint(
            "from_line_code <> to_line_code",
            name="ck_comparative_reclassifications_different_lines",
        ),
        sa.CheckConstraint("amount <> 0", name="ck_comparative_reclassifications_nonzero_amount"),
        sa.CheckConstraint(
            "length(trim(reason)) > 0", name="ck_comparative_reclassifications_reason"
        ),
    )
    op.create_index(
        "ix_comparative_reclass_company_snapshot",
        "comparative_reclassifications",
        ["company_id", "comparative_statement_id"],
    )
    op.create_table(
        "comparative_statement_audit_events",
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("comparative_statement_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comparative_statement_audit_events")),
        sa.ForeignKeyConstraint(
            ["company_id", "comparative_statement_id"],
            ["comparative_statement_snapshots.company_id", "comparative_statement_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_comparative_statement_audit_events_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "expected_version > 0", name="ck_comparative_statement_audit_events_expected_version"
        ),
    )
    op.create_index(
        "ix_comparative_audit_company_snapshot",
        "comparative_statement_audit_events",
        ["company_id", "comparative_statement_id"],
    )
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"), "report_generation_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS',"
        "'CASH_FLOW','CHANGES_IN_EQUITY','NOTES','COMPARATIVE_FINANCIAL_STATEMENTS')",
    )
    op.add_column(
        "report_generation_runs",
        sa.Column("comparative_statement_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "report_generation_runs",
        sa.Column("comparison_period_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_report_generation_runs_comparison_period",
        "report_generation_runs",
        "accounting_periods",
        ["company_id", "comparison_period_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_report_generation_runs_comparative_statement",
        "report_generation_runs",
        "comparative_statement_snapshots",
        ["company_id", "comparative_statement_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_comparative_source"),
        "report_generation_runs",
        "(report_code = 'COMPARATIVE_FINANCIAL_STATEMENTS' AND "
        "comparison_period_id IS NOT NULL AND comparative_statement_id IS NOT NULL) OR "
        "(report_code <> 'COMPARATIVE_FINANCIAL_STATEMENTS' AND "
        "comparison_period_id IS NULL AND comparative_statement_id IS NULL)",
    )
    op.execute("""
CREATE FUNCTION comparative_statement_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.company_id, NEW.period_id, NEW.comparison_period_id, NEW.statement_set_id,
        NEW.comparison_statement_set_id, NEW.close_version, NEW.comparison_close_version,
        NEW.current_source_digest, NEW.comparison_source_digest, NEW.current_mapping_digest,
        NEW.comparison_mapping_digest, NEW.taxonomy_version, NEW.source_digest, NEW.created_by)
       IS DISTINCT FROM
       (OLD.company_id, OLD.period_id, OLD.comparison_period_id, OLD.statement_set_id,
        OLD.comparison_statement_set_id, OLD.close_version, OLD.comparison_close_version,
        OLD.current_source_digest, OLD.comparison_source_digest, OLD.current_mapping_digest,
        OLD.comparison_mapping_digest, OLD.taxonomy_version, OLD.source_digest, OLD.created_by)
       OR OLD.status IN ('APPROVED','REJECTED')
       OR NEW.version <> OLD.version + 1
       OR NOT ((OLD.status = 'DRAFT' AND NEW.status IN ('DRAFT','REVIEW_REQUESTED'))
            OR (OLD.status = 'REVIEW_REQUESTED' AND NEW.status IN ('APPROVED','REJECTED'))) THEN
        RAISE EXCEPTION 'comparative statement state is immutable or transition is invalid';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER comparative_statement_guard
BEFORE UPDATE ON comparative_statement_snapshots
FOR EACH ROW EXECUTE FUNCTION comparative_statement_guard();
CREATE FUNCTION comparative_statement_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_id uuid; parent_company uuid; parent_status text;
BEGIN
    parent_id := COALESCE(NEW.snapshot_id, OLD.snapshot_id);
    parent_company := COALESCE(NEW.company_id, OLD.company_id);
    SELECT cs.status INTO parent_status
      FROM comparative_statement_snapshots cs
      JOIN financial_statement_snapshots fs
        ON fs.company_id = cs.company_id AND fs.comparative_statement_id = cs.id
      WHERE fs.company_id = parent_company AND fs.id = parent_id;
    IF parent_status IS NOT NULL AND parent_status <> 'DRAFT' THEN
        RAISE EXCEPTION 'comparative statement lines are frozen';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;
CREATE TRIGGER comparative_statement_line_guard
BEFORE INSERT OR UPDATE OR DELETE ON financial_statement_lines
FOR EACH ROW EXECUTE FUNCTION comparative_statement_line_guard();
CREATE FUNCTION comparative_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_id uuid; parent_company uuid; parent_status text;
BEGIN
    parent_id := COALESCE(NEW.comparative_statement_id, OLD.comparative_statement_id);
    parent_company := COALESCE(NEW.company_id, OLD.company_id);
    SELECT status INTO parent_status FROM comparative_statement_snapshots
      WHERE company_id = parent_company AND id = parent_id FOR UPDATE;
    IF parent_status <> 'DRAFT' THEN
        RAISE EXCEPTION 'comparative statement lines and reclassifications are frozen';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;
CREATE TRIGGER comparative_reclassification_guard
BEFORE INSERT OR UPDATE OR DELETE ON comparative_reclassifications
FOR EACH ROW EXECUTE FUNCTION comparative_child_guard();
CREATE FUNCTION comparative_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'comparative statement audit is immutable';
END;
$$;
CREATE TRIGGER comparative_audit_immutable
BEFORE UPDATE OR DELETE ON comparative_statement_audit_events
FOR EACH ROW EXECUTE FUNCTION comparative_audit_immutable();
""")


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_report_generation_runs_comparative_source"),
        "report_generation_runs",
        type_="check",
    )
    op.drop_constraint(
        "fk_report_generation_runs_comparative_statement",
        "report_generation_runs",
        type_="foreignkey",
    )
    op.drop_column("report_generation_runs", "comparative_statement_id")
    op.drop_constraint(
        "fk_report_generation_runs_comparison_period", "report_generation_runs", type_="foreignkey"
    )
    op.drop_column("report_generation_runs", "comparison_period_id")
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"), "report_generation_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS',"
        "'CASH_FLOW','CHANGES_IN_EQUITY','NOTES')",
    )
    op.execute("DROP FUNCTION comparative_audit_immutable() CASCADE")
    op.execute("DROP FUNCTION comparative_child_guard() CASCADE")
    op.execute("DROP FUNCTION comparative_statement_line_guard() CASCADE")
    op.execute("DROP FUNCTION comparative_statement_guard() CASCADE")
    op.drop_constraint(
        "ck_financial_statement_lines_comparative_amounts",
        "financial_statement_lines",
        type_="check",
    )
    op.drop_constraint(
        "fk_financial_statement_lines_prior_source_line",
        "financial_statement_lines",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_financial_statement_lines_current_source_line",
        "financial_statement_lines",
        type_="foreignkey",
    )
    op.drop_column("financial_statement_lines", "prior_source_line_id")
    op.drop_column("financial_statement_lines", "current_source_line_id")
    op.drop_column("financial_statement_lines", "presentation_amount")
    op.drop_column("financial_statement_lines", "prior_amount")
    op.drop_constraint(
        "fk_financial_statement_snapshots_comparative_statement",
        "financial_statement_snapshots",
        type_="foreignkey",
    )
    op.drop_column("financial_statement_snapshots", "comparative_statement_id")
    op.drop_index(
        "ix_comparative_audit_company_snapshot", table_name="comparative_statement_audit_events"
    )
    op.drop_table("comparative_statement_audit_events")
    op.drop_index(
        "ix_comparative_reclass_company_snapshot", table_name="comparative_reclassifications"
    )
    op.drop_table("comparative_reclassifications")
    op.drop_index(
        "ix_comparative_statements_company_period", table_name="comparative_statement_snapshots"
    )
    op.drop_table("comparative_statement_snapshots")
