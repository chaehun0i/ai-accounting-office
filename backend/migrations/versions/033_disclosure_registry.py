# ruff: noqa: E501
"""Add relational disclosure registry, source facts and review audit."""

from collections.abc import Sequence
from datetime import date
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "033_disclosure_registry"
down_revision: str | Sequence[str] | None = "032_equity_report_export"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS',"
        "'CASH_FLOW','CHANGES_IN_EQUITY','NOTES')",
    )
    op.create_table(
        "disclosure_templates",
        sa.Column("framework_code", sa.String(32), nullable=False),
        sa.Column("template_code", sa.String(48), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disclosure_templates")),
        sa.UniqueConstraint(
            "framework_code",
            "template_code",
            "version",
            name=op.f("uq_disclosure_templates_framework_code_template_code_version"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_disclosure_templates_version")),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name=op.f("ck_disclosure_templates_status")
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_disclosure_templates_dates"),
        ),
    )
    op.create_table(
        "disclosure_sections",
        sa.Column("template_id", UUID(as_uuid=True), nullable=False),
        sa.Column("section_code", sa.String(48), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("requirement_rule_key", sa.String(48), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disclosure_sections")),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["disclosure_templates.id"],
            name=op.f("fk_disclosure_sections_template_id_disclosure_templates"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "template_id", "id", name=op.f("uq_disclosure_sections_template_id_id")
        ),
        sa.UniqueConstraint(
            "template_id",
            "section_code",
            name=op.f("uq_disclosure_sections_template_id_section_code"),
        ),
        sa.CheckConstraint("display_order > 0", name=op.f("ck_disclosure_sections_display_order")),
    )
    op.create_table(
        "disclosure_fields",
        sa.Column("template_id", UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", UUID(as_uuid=True), nullable=False),
        sa.Column("field_code", sa.String(48), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("data_type", sa.String(12), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("source_fact_type", sa.String(32), nullable=False),
        sa.Column("aggregation_handler_key", sa.String(48), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disclosure_fields")),
        sa.ForeignKeyConstraint(
            ["template_id", "section_id"],
            ["disclosure_sections.template_id", "disclosure_sections.id"],
            name=op.f("fk_disclosure_fields_template_section"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("template_id", "id", name=op.f("uq_disclosure_fields_template_id_id")),
        sa.UniqueConstraint("section_id", "id", name=op.f("uq_disclosure_fields_section_id_id")),
        sa.UniqueConstraint(
            "section_id", "field_code", name=op.f("uq_disclosure_fields_section_id_field_code")
        ),
        sa.CheckConstraint(
            "data_type IN ('TEXT','DECIMAL','DATE','BOOLEAN')",
            name=op.f("ck_disclosure_fields_data_type"),
        ),
        sa.CheckConstraint(
            "source_fact_type IN ('STATEMENT_LINE','CASH_FLOW_LINE','EQUITY_LINE')",
            name=op.f("ck_disclosure_fields_source_fact"),
        ),
    )
    op.create_table(
        "disclosure_instances",
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("statement_set_id", UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("balance_sheet_digest", sa.String(64), nullable=False),
        sa.Column("income_statement_digest", sa.String(64), nullable=False),
        sa.Column("cash_flow_digest", sa.String(64), nullable=False),
        sa.Column("equity_digest", sa.String(64), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("reconciliation_status", sa.String(16), nullable=False),
        sa.Column("reconciliation_digest", sa.String(64), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disclosure_instances")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_disclosure_instances_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            name=op.f("fk_disclosure_instances_statement_set_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            name=op.f("fk_disclosure_instances_period_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["disclosure_templates.id"],
            name=op.f("fk_disclosure_instances_template_id_disclosure_templates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_disclosure_instances_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name=op.f("fk_disclosure_instances_approved_by_users"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_disclosure_instances_company_id_id")),
        sa.UniqueConstraint(
            "company_id",
            "period_id",
            "source_digest",
            "revision",
            name=op.f("uq_disclosure_instances_source_revision"),
        ),
        sa.CheckConstraint(
            "template_version > 0 AND revision > 0 AND version > 0",
            name=op.f("ck_disclosure_instances_version"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','BLOCKED','REVIEW_REQUESTED','APPROVED','REJECTED')",
            name=op.f("ck_disclosure_instances_status"),
        ),
        sa.CheckConstraint(
            "reconciliation_status = 'RECONCILED'",
            name=op.f("ck_disclosure_instances_reconciliation_status"),
        ),
        sa.CheckConstraint(
            "(status = 'APPROVED' AND approved_by IS NOT NULL AND approved_at IS NOT NULL) OR "
            "(status <> 'APPROVED' AND approved_by IS NULL AND approved_at IS NULL)",
            name=op.f("ck_disclosure_instances_approval_fields"),
        ),
    )
    op.create_table(
        "disclosure_values",
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("instance_id", UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", UUID(as_uuid=True), nullable=False),
        sa.Column("field_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("statement_line_id", UUID(as_uuid=True), nullable=True),
        sa.Column("cash_flow_line_id", UUID(as_uuid=True), nullable=True),
        sa.Column("equity_line_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_code", sa.String(60), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("decimal_value", sa.Numeric(28, 4), nullable=True),
        sa.Column("date_value", sa.Date(), nullable=True),
        sa.Column("boolean_value", sa.Boolean(), nullable=True),
        sa.Column("validation_status", sa.String(16), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disclosure_values")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_disclosure_values_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "instance_id"],
            ["disclosure_instances.company_id", "disclosure_instances.id"],
            name=op.f("fk_disclosure_values_instance_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_line_id"],
            ["financial_statement_lines.company_id", "financial_statement_lines.id"],
            name=op.f("fk_disclosure_values_statement_line_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "cash_flow_line_id"],
            ["cash_flow_lines.company_id", "cash_flow_lines.id"],
            name=op.f("fk_disclosure_values_cash_flow_line_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "equity_line_id"],
            ["equity_statement_lines.company_id", "equity_statement_lines.id"],
            name=op.f("fk_disclosure_values_equity_line_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "field_id"],
            ["disclosure_fields.section_id", "disclosure_fields.id"],
            name=op.f("fk_disclosure_values_section_field"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_disclosure_values_company_id_id")),
        sa.UniqueConstraint(
            "instance_id",
            "source_type",
            "source_id",
            name=op.f("uq_disclosure_values_instance_source"),
        ),
        sa.CheckConstraint(
            "source_type IN ('BALANCE_SHEET','INCOME_STATEMENT','CASH_FLOW','CHANGES_IN_EQUITY')",
            name=op.f("ck_disclosure_values_source_type"),
        ),
        sa.CheckConstraint(
            "(source_type IN ('BALANCE_SHEET','INCOME_STATEMENT') AND statement_line_id = source_id AND cash_flow_line_id IS NULL AND equity_line_id IS NULL) OR (source_type = 'CASH_FLOW' AND statement_line_id IS NULL AND cash_flow_line_id = source_id AND equity_line_id IS NULL) OR (source_type = 'CHANGES_IN_EQUITY' AND statement_line_id IS NULL AND cash_flow_line_id IS NULL AND equity_line_id = source_id)",
            name=op.f("ck_disclosure_values_source_reference"),
        ),
        sa.CheckConstraint(
            "validation_status = 'VALIDATED'", name=op.f("ck_disclosure_values_validation_status")
        ),
        sa.CheckConstraint(
            "num_nonnulls(text_value, decimal_value, date_value, boolean_value) = 1",
            name=op.f("ck_disclosure_values_one_typed_value"),
        ),
    )
    op.create_table(
        "disclosure_audit_events",
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("instance_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disclosure_audit_events")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_disclosure_audit_events_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "instance_id"],
            ["disclosure_instances.company_id", "disclosure_instances.id"],
            name=op.f("fk_disclosure_audit_events_instance_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_disclosure_audit_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("expected_version > 0", name=op.f("ck_disclosure_audit_events_version")),
    )
    op.create_table(
        "disclosure_narratives",
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("instance_id", UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", UUID(as_uuid=True), nullable=False),
        sa.Column("text_value", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disclosure_narratives")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_disclosure_narratives_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "instance_id"],
            ["disclosure_instances.company_id", "disclosure_instances.id"],
            name=op.f("fk_disclosure_narratives_instance_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["disclosure_sections.id"],
            name=op.f("fk_disclosure_narratives_section_id_disclosure_sections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_disclosure_narratives_updated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name=op.f("uq_disclosure_narratives_company_id_id")
        ),
        sa.UniqueConstraint(
            "instance_id",
            "section_id",
            name=op.f("uq_disclosure_narratives_instance_id_section_id"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','APPROVED') AND version > 0",
            name=op.f("ck_disclosure_narratives_status"),
        ),
    )
    op.create_table(
        "disclosure_commands",
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("instance_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disclosure_commands")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_disclosure_commands_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_disclosure_commands_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "instance_id"],
            ["disclosure_instances.company_id", "disclosure_instances.id"],
            name=op.f("fk_disclosure_commands_instance_scope"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "actor_id",
            "idempotency_key",
            name=op.f("uq_disclosure_commands_company_actor_key"),
        ),
    )
    op.create_index(
        "ix_disclosure_instances_company_period",
        "disclosure_instances",
        ["company_id", "period_id"],
    )
    op.create_index(
        "ix_disclosure_values_company_instance",
        "disclosure_values",
        ["company_id", "instance_id"],
    )
    op.create_index(
        "ix_disclosure_audit_company_instance",
        "disclosure_audit_events",
        ["company_id", "instance_id"],
    )
    op.execute("""
CREATE FUNCTION disclosure_immutable_rows() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'disclosure snapshot rows are immutable';
END;
$$;
CREATE TRIGGER immutable_disclosure_values
BEFORE UPDATE OR DELETE ON disclosure_values
FOR EACH ROW EXECUTE FUNCTION disclosure_immutable_rows();
CREATE TRIGGER immutable_disclosure_audit
BEFORE UPDATE OR DELETE ON disclosure_audit_events
FOR EACH ROW EXECUTE FUNCTION disclosure_immutable_rows();
CREATE TRIGGER immutable_disclosure_commands
BEFORE UPDATE OR DELETE ON disclosure_commands
FOR EACH ROW EXECUTE FUNCTION disclosure_immutable_rows();
CREATE FUNCTION disclosure_instance_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'APPROVED' OR
       (NEW.company_id, NEW.statement_set_id, NEW.period_id, NEW.template_id,
        NEW.template_version, NEW.revision, NEW.balance_sheet_digest,
        NEW.income_statement_digest, NEW.cash_flow_digest, NEW.equity_digest,
        NEW.source_digest, NEW.reconciliation_status, NEW.reconciliation_digest,
        NEW.created_by, NEW.created_at)
       IS DISTINCT FROM
       (OLD.company_id, OLD.statement_set_id, OLD.period_id, OLD.template_id,
        OLD.template_version, OLD.revision, OLD.balance_sheet_digest,
        OLD.income_statement_digest, OLD.cash_flow_digest, OLD.equity_digest,
        OLD.source_digest, OLD.reconciliation_status, OLD.reconciliation_digest,
        OLD.created_by, OLD.created_at) THEN
        RAISE EXCEPTION 'disclosure source identity is immutable';
    END IF;
    IF NEW.version <> OLD.version + 1 OR
       NOT ((OLD.status IN ('DRAFT','REJECTED') AND NEW.status = OLD.status) OR
            (OLD.status IN ('DRAFT','REJECTED') AND NEW.status = 'REVIEW_REQUESTED') OR
            (OLD.status = 'REVIEW_REQUESTED' AND NEW.status IN ('APPROVED','REJECTED'))) THEN
        RAISE EXCEPTION 'disclosure state transition is invalid';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER disclosure_instance_guard
BEFORE UPDATE ON disclosure_instances
FOR EACH ROW EXECUTE FUNCTION disclosure_instance_guard();
CREATE FUNCTION disclosure_narrative_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'APPROVED' THEN
        RAISE EXCEPTION 'approved disclosure narrative is immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER disclosure_narrative_guard
BEFORE UPDATE OR DELETE ON disclosure_narratives
FOR EACH ROW EXECUTE FUNCTION disclosure_narrative_guard();
""")
    template_id = uuid4()
    section_ids = [uuid4() for _ in range(4)]
    field_ids = [uuid4() for _ in range(4)]
    op.execute(
        sa.text("""INSERT INTO disclosure_templates
        (id,framework_code,template_code,title,version,status,effective_from,effective_to)
        VALUES (:id,'INTERNAL','INTERNAL_CORE_NOTES','내부 검증용 재무제표 주석',1,'ACTIVE',:start,NULL)""").bindparams(
            id=template_id, start=date(1900, 1, 1)
        )
    )
    sections = [
        ("BALANCE_SHEET", "재무상태표 Fact", "STATEMENT_LINE"),
        ("INCOME_STATEMENT", "손익계산서 Fact", "STATEMENT_LINE"),
        ("CASH_FLOW", "현금흐름표 Fact", "CASH_FLOW_LINE"),
        ("CHANGES_IN_EQUITY", "자본변동표 Fact", "EQUITY_LINE"),
    ]
    for index, (code, title, fact_type) in enumerate(sections):
        op.execute(
            sa.text("""INSERT INTO disclosure_sections
            (id,template_id,section_code,title,display_order,requirement_rule_key)
            VALUES (:id,:template,:code,:title,:order,'SOURCE_STATEMENT_REQUIRED')""").bindparams(
                id=section_ids[index], template=template_id, code=code, title=title, order=index + 1
            )
        )
        op.execute(
            sa.text("""INSERT INTO disclosure_fields
            (id,template_id,section_id,field_code,label,data_type,required,source_fact_type,aggregation_handler_key)
            VALUES (:id,:template,:section,'SOURCE_LINE_AMOUNT','원천 제표 항목 금액','DECIMAL',TRUE,:fact,'COPY_VERIFIED_LINE')""").bindparams(
                id=field_ids[index],
                template=template_id,
                section=section_ids[index],
                fact=fact_type,
            )
        )


def downgrade() -> None:
    op.drop_table("disclosure_commands")
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS',"
        "'CASH_FLOW','CHANGES_IN_EQUITY')",
    )
    op.execute("DROP FUNCTION disclosure_narrative_guard() CASCADE")
    op.execute("DROP FUNCTION disclosure_instance_guard() CASCADE")
    op.execute("DROP FUNCTION disclosure_immutable_rows() CASCADE")
    op.drop_index("ix_disclosure_audit_company_instance", table_name="disclosure_audit_events")
    op.drop_index("ix_disclosure_values_company_instance", table_name="disclosure_values")
    op.drop_index("ix_disclosure_instances_company_period", table_name="disclosure_instances")
    op.drop_table("disclosure_narratives")
    op.drop_table("disclosure_audit_events")
    op.drop_table("disclosure_values")
    op.drop_table("disclosure_instances")
    op.drop_table("disclosure_fields")
    op.drop_table("disclosure_sections")
    op.drop_table("disclosure_templates")
