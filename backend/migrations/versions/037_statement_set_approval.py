"""Append-only independent review for SCE snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "037_statement_set_approval"
down_revision = "036_dividend_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"), "report_generation_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS','CASH_FLOW',"
        "'CHANGES_IN_EQUITY','NOTES','COMPARATIVE_FINANCIAL_STATEMENTS','FINANCIAL_STATEMENT_SET')",
    )

    op.execute(
        """
CREATE TABLE statement_set_revisions (
	company_id UUID NOT NULL,
	period_id UUID NOT NULL,
	statement_set_id UUID NOT NULL,
	balance_id UUID NOT NULL,
	income_id UUID NOT NULL,
	cash_id UUID NOT NULL,
	equity_id UUID NOT NULL,
	notes_id UUID NOT NULL,
	snapshot_digest VARCHAR(64) NOT NULL,
	generated_by UUID NOT NULL,
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	id UUID NOT NULL,
	CONSTRAINT pk_statement_set_revisions PRIMARY KEY (id),
	CONSTRAINT uq_statement_set_revisions_company_id_id UNIQUE (company_id, id),
	CONSTRAINT uq_statement_set_revisions_company_id_period_id_snapshot_digest
        UNIQUE (company_id, period_id, snapshot_digest),
	CONSTRAINT fk_statement_set_revisions_company_id_period_id_account_a731
        FOREIGN KEY(company_id, period_id)
        REFERENCES accounting_periods (company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_revisions_company_id_statement_set_id__be78
        FOREIGN KEY(company_id, statement_set_id)
        REFERENCES financial_statement_sets (company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_revisions_company_id_balance_id_financ_fb83
        FOREIGN KEY(company_id, balance_id)
        REFERENCES financial_statements (company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_revisions_company_id_income_id_financi_4456
        FOREIGN KEY(company_id, income_id)
        REFERENCES financial_statements (company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_revisions_company_id_cash_id_cash_flow_a353
        FOREIGN KEY(company_id, cash_id)
        REFERENCES cash_flow_statements (company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_revisions_company_id_equity_id_stateme_3b62
        FOREIGN KEY(company_id, equity_id)
        REFERENCES statement_of_changes_in_equity (company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_revisions_company_id_notes_id_disclosu_c7d3
        FOREIGN KEY(company_id, notes_id)
        REFERENCES disclosure_instances (company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_revisions_company_id_companies
        FOREIGN KEY(company_id)
        REFERENCES companies (id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_revisions_generated_by_users
        FOREIGN KEY(generated_by)
        REFERENCES users (id) ON DELETE RESTRICT
)

"""
    )
    op.create_table(
        "statement_set_review_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("statement_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "statement_id", "version"),
        sa.UniqueConstraint("company_id", "actor_id", "idempotency_key"),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["statement_set_revisions.company_id", "statement_set_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version > 0 AND length(trim(reason)) > 0", name="input"),
        sa.CheckConstraint("status IN ('REVIEW_REQUESTED','APPROVED','REJECTED')", name="status"),
        sa.CheckConstraint(
            "status = 'REVIEW_REQUESTED' OR actor_id <> requested_by", name="separation"
        ),
    )
    op.execute("""
    CREATE FUNCTION statement_set_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE snapshot_row record; prior_row record;
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Equity review is immutable' USING ERRCODE='23514';
      END IF;
      SELECT * INTO snapshot_row FROM statement_set_revisions
        WHERE company_id=NEW.company_id AND id=NEW.statement_id FOR UPDATE;
      IF NOT FOUND OR NEW.source_digest <> snapshot_row.snapshot_digest THEN
        RAISE EXCEPTION 'Equity source mismatch' USING ERRCODE='23514';
      END IF;
      SELECT * INTO prior_row FROM statement_set_review_events
        WHERE company_id=NEW.company_id AND statement_id=NEW.statement_id
        ORDER BY version DESC LIMIT 1;
      IF NEW.version <> COALESCE(prior_row.version, 0) + 1 THEN
        RAISE EXCEPTION 'Equity review version conflict' USING ERRCODE='23514';
      END IF;
      IF NEW.status='REVIEW_REQUESTED' THEN
        IF NEW.actor_id <> NEW.requested_by OR
           (prior_row.id IS NOT NULL AND prior_row.status <> 'REJECTED') THEN
          RAISE EXCEPTION 'Invalid review request' USING ERRCODE='23514';
        END IF;
      ELSIF prior_row.id IS NULL OR prior_row.status <> 'REVIEW_REQUESTED' OR
        NEW.requested_by <> prior_row.requested_by OR NEW.actor_id=NEW.requested_by OR
        NEW.actor_id=snapshot_row.generated_by THEN
        RAISE EXCEPTION 'Independent review required' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER statement_set_review_guard BEFORE INSERT OR UPDATE OR DELETE
    ON statement_set_review_events
    FOR EACH ROW EXECUTE FUNCTION statement_set_review_guard();
    """)

    op.execute("""
    CREATE FUNCTION statement_set_members_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM financial_statements b JOIN financial_statements i
          ON i.company_id=b.company_id AND i.statement_set_id=b.statement_set_id
          JOIN cash_flow_statements c ON c.company_id=b.company_id
          AND c.statement_set_id=b.statement_set_id
          JOIN statement_of_changes_in_equity e ON e.company_id=b.company_id
          AND e.statement_set_id=b.statement_set_id
          JOIN disclosure_instances n ON n.company_id=b.company_id
          AND n.statement_set_id=b.statement_set_id
          JOIN financial_statement_sets s ON s.company_id=b.company_id AND s.id=b.statement_set_id
          WHERE b.company_id=NEW.company_id AND b.id=NEW.balance_id
          AND i.id=NEW.income_id AND b.statement_type='BALANCE_SHEET'
          AND i.statement_type='INCOME_STATEMENT' AND c.id=NEW.cash_id AND e.id=NEW.equity_id
          AND n.id=NEW.notes_id AND n.status='APPROVED'
          AND s.id=NEW.statement_set_id AND s.period_id=NEW.period_id
          AND c.period_id=NEW.period_id AND e.period_id=NEW.period_id
          AND n.period_id=NEW.period_id) THEN
        RAISE EXCEPTION 'Set member scope mismatch' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER statement_set_members BEFORE INSERT ON statement_set_revisions
    FOR EACH ROW EXECUTE FUNCTION statement_set_members_guard();
    """)
    op.execute("""
    CREATE FUNCTION statement_set_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Statement set revision is immutable' USING ERRCODE='23514'; END $$;
    CREATE TRIGGER statement_set_revision_immutable BEFORE UPDATE OR DELETE
    ON statement_set_revisions
    FOR EACH ROW EXECUTE FUNCTION statement_set_revision_guard();""")

    op.execute("""
CREATE TABLE statement_set_commands (
	company_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	idempotency_key VARCHAR(100) NOT NULL,
	fingerprint VARCHAR(64) NOT NULL,
	statement_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	id UUID NOT NULL,
	CONSTRAINT pk_statement_set_commands PRIMARY KEY (id),
	CONSTRAINT uq_statement_set_commands_company_id_actor_id_idempotency_key
        UNIQUE (company_id, actor_id, idempotency_key),
	CONSTRAINT fk_statement_set_commands_company_id_statement_id_state_e987
        FOREIGN KEY(company_id, statement_id)
        REFERENCES statement_set_revisions (company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_commands_company_id_companies
        FOREIGN KEY(company_id)
        REFERENCES companies (id) ON DELETE RESTRICT,
	CONSTRAINT fk_statement_set_commands_actor_id_users
        FOREIGN KEY(actor_id)
        REFERENCES users (id) ON DELETE RESTRICT
)

""")


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_report_generation_runs_report_code"), "report_generation_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_report_generation_runs_report_code"),
        "report_generation_runs",
        "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS','CASH_FLOW',"
        "'CHANGES_IN_EQUITY','NOTES','COMPARATIVE_FINANCIAL_STATEMENTS')",
    )

    op.drop_table("statement_set_review_events")
    op.execute("DROP FUNCTION statement_set_review_guard()")

    op.drop_table("statement_set_commands")
    op.drop_table("statement_set_revisions")
    op.execute("DROP FUNCTION statement_set_revision_guard()")

    op.execute("DROP FUNCTION statement_set_members_guard()")
