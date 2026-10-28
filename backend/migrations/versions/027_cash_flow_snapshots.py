"""Immutable reconciled cash flow statements and relational provenance.

Revision ID: 027_cash_flow_snapshots
Revises: 026_cash_flow_indirect
"""

from collections.abc import Sequence

from alembic import op

revision: str = "027_cash_flow_snapshots"
down_revision: str | Sequence[str] | None = "026_cash_flow_indirect"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE cash_flow_statements (
        company_id UUID NOT NULL,
        period_id UUID NOT NULL,
        statement_set_id UUID NOT NULL,
        balance_sheet_id UUID NOT NULL,
        balance_sheet_digest VARCHAR(64) NOT NULL,
        income_statement_id UUID NOT NULL,
        income_statement_digest VARCHAR(64) NOT NULL,
        close_version INTEGER NOT NULL,
        source_digest VARCHAR(64) NOT NULL,
        mapping_digest VARCHAR(64) NOT NULL,
        direct_mapping_digest VARCHAR(64) NOT NULL,
        snapshot_digest VARCHAR(64) NOT NULL,
        policy_code VARCHAR(40) NOT NULL,
        policy_version INTEGER NOT NULL,
        method VARCHAR(16) NOT NULL,
        status VARCHAR(16) NOT NULL,
        opening_cash NUMERIC(28, 4) NOT NULL,
        closing_cash NUMERIC(28, 4) NOT NULL,
        net_profit NUMERIC(28, 4) NOT NULL,
        net_operating NUMERIC(28, 4) NOT NULL,
        net_investing NUMERIC(28, 4) NOT NULL,
        net_financing NUMERIC(28, 4) NOT NULL,
        exchange_effect NUMERIC(28, 4) NOT NULL,
        generated_by UUID NOT NULL,
        generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        generation_transaction BIGINT DEFAULT txid_current() NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_cash_flow_statements PRIMARY KEY (id),
        CONSTRAINT uq_cash_flow_statements_company_id_id UNIQUE (company_id, id),
        CONSTRAINT uq_cash_flow_statements_company_id_statement_set_id_map_e942 UNIQUE
(company_id, statement_set_id, mapping_digest),
        CONSTRAINT fk_cash_flow_statements_company_id_period_id_accounting_periods FOREIGN
KEY(company_id, period_id) REFERENCES accounting_periods (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_cash_flow_statements_company_id_statement_set_id_fin_bf7f FOREIGN
KEY(company_id, statement_set_id) REFERENCES financial_statement_sets (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_statements_company_id_balance_sheet_id_fin_1cc5 FOREIGN
KEY(company_id, balance_sheet_id) REFERENCES financial_statements (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_statements_company_id_income_statement_id__4e23 FOREIGN
KEY(company_id, income_statement_id) REFERENCES financial_statements (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_statements_generated_by_users FOREIGN KEY(generated_by)
REFERENCES users (id) ON DELETE RESTRICT,
        CONSTRAINT ck_cash_flow_statements_state CHECK (method = 'INDIRECT' AND status =
'RECONCILED'),
        CONSTRAINT ck_cash_flow_statements_versions CHECK (close_version >= 1 AND policy_version
>= 1),
        CONSTRAINT ck_cash_flow_statements_reconciliation CHECK (opening_cash + net_operating +
net_investing + net_financing + exchange_effect = closing_cash)
)
""")
    op.execute("""
CREATE TABLE cash_flow_adjustments (
        company_id UUID NOT NULL,
        statement_id UUID NOT NULL,
        rule_id UUID NOT NULL,
        rule_version INTEGER NOT NULL,
        account_id UUID NOT NULL,
        adjustment_code VARCHAR(30) NOT NULL,
        opening_balance NUMERIC(28, 4) NOT NULL,
        closing_balance NUMERIC(28, 4) NOT NULL,
        amount NUMERIC(28, 4) NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_cash_flow_adjustments PRIMARY KEY (id),
        CONSTRAINT uq_cash_flow_adjustments_company_id_id UNIQUE (company_id, id),
        CONSTRAINT uq_cash_flow_adjustments_company_id_statement_id_id UNIQUE (company_id,
statement_id, id),
        CONSTRAINT uq_cash_flow_adjustments_statement_id_account_id UNIQUE (statement_id,
account_id),
        CONSTRAINT fk_cash_flow_adjustments_company_id_statement_id_cash_f_5fe2 FOREIGN
KEY(company_id, statement_id) REFERENCES cash_flow_statements (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_adjustments_company_id_rule_id_cash_flow_a_ca8b FOREIGN
KEY(company_id, rule_id) REFERENCES cash_flow_adjustment_rules (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_adjustments_company_id_account_id_chart_of_9440 FOREIGN
KEY(company_id, account_id) REFERENCES chart_of_accounts (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_cash_flow_adjustments_version CHECK (rule_version >= 1)
)
""")
    op.execute("""
CREATE TABLE cash_flow_balance_sources (
        company_id UUID NOT NULL,
        statement_id UUID NOT NULL,
        scope_id UUID NOT NULL,
        scope_version INTEGER NOT NULL,
        account_id UUID NOT NULL,
        journal_id UUID NOT NULL,
        journal_line_id UUID NOT NULL,
        entry_date DATE NOT NULL,
        signed_debit_amount NUMERIC(28, 4) NOT NULL,
        is_opening BOOLEAN NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_cash_flow_balance_sources PRIMARY KEY (id),
        CONSTRAINT uq_cash_flow_balance_sources_statement_id_journal_line_id UNIQUE
(statement_id, journal_line_id),
        CONSTRAINT fk_cash_flow_balance_sources_company_id_statement_id_ca_2c7e FOREIGN
KEY(company_id, statement_id) REFERENCES cash_flow_statements (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_balance_sources_company_id_scope_id_cash_s_72af FOREIGN
KEY(company_id, scope_id) REFERENCES cash_scope_mappings (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_cash_flow_balance_sources_company_id_account_id_char_49f0 FOREIGN
KEY(company_id, account_id) REFERENCES chart_of_accounts (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_cash_flow_balance_sources_company_id_journal_id_jour_6a43 FOREIGN
KEY(company_id, journal_id, journal_line_id) REFERENCES journal_lines (company_id,
journal_entry_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_cash_flow_balance_sources_version CHECK (scope_version >= 1)
)
""")
    op.execute("""
CREATE TABLE cash_flow_commands (
        company_id UUID NOT NULL,
        actor_id UUID NOT NULL,
        idempotency_key VARCHAR(100) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL,
        statement_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_cash_flow_commands PRIMARY KEY (id),
        CONSTRAINT uq_cash_flow_commands_company_id_actor_id_idempotency_key UNIQUE (company_id,
actor_id, idempotency_key),
        CONSTRAINT fk_cash_flow_commands_company_id_statement_id_cash_flow_ec17 FOREIGN
KEY(company_id, statement_id) REFERENCES cash_flow_statements (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_commands_actor_id_users FOREIGN KEY(actor_id) REFERENCES users
(id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE cash_flow_journal_traces (
        company_id UUID NOT NULL,
        statement_id UUID NOT NULL,
        journal_id UUID NOT NULL,
        transaction_id UUID,
        id UUID NOT NULL,
        CONSTRAINT pk_cash_flow_journal_traces PRIMARY KEY (id),
        CONSTRAINT uq_cash_flow_journal_traces_company_id_id UNIQUE (company_id, id),
        CONSTRAINT uq_cash_flow_journal_traces_statement_id_journal_id UNIQUE (statement_id,
journal_id),
        CONSTRAINT fk_cash_flow_journal_traces_company_id_statement_id_cas_4853 FOREIGN
KEY(company_id, statement_id) REFERENCES cash_flow_statements (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_journal_traces_company_id_journal_id_journ_488b FOREIGN
KEY(company_id, journal_id) REFERENCES journal_entries (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_cash_flow_journal_traces_company_id_transaction_id_t_8e75 FOREIGN
KEY(company_id, transaction_id) REFERENCES transactions (company_id, id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE cash_flow_adjustment_sources (
        company_id UUID NOT NULL,
        adjustment_id UUID NOT NULL,
        journal_id UUID NOT NULL,
        journal_line_id UUID NOT NULL,
        entry_date DATE NOT NULL,
        signed_debit_amount NUMERIC(28, 4) NOT NULL,
        is_opening BOOLEAN NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_cash_flow_adjustment_sources PRIMARY KEY (id),
        CONSTRAINT uq_cash_flow_adjustment_sources_adjustment_id_journal_line_id UNIQUE
(adjustment_id, journal_line_id),
        CONSTRAINT fk_cash_flow_adjustment_sources_company_id_adjustment_i_7717 FOREIGN
KEY(company_id, adjustment_id) REFERENCES cash_flow_adjustments (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_adjustment_sources_company_id_journal_id_j_9c6d FOREIGN
KEY(company_id, journal_id, journal_line_id) REFERENCES journal_lines (company_id,
journal_entry_id, id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE cash_flow_events (
        company_id UUID NOT NULL,
        statement_id UUID NOT NULL,
        journal_id UUID NOT NULL,
        cash_line_id UUID NOT NULL,
        cash_account_id UUID NOT NULL,
        counterpart_line_id UUID NOT NULL,
        counterpart_account_id UUID NOT NULL,
        activity_type VARCHAR(20) NOT NULL,
        line_code VARCHAR(40) NOT NULL,
        cash_inflow NUMERIC(28, 4) NOT NULL,
        cash_outflow NUMERIC(28, 4) NOT NULL,
        classification_id UUID NOT NULL,
        classification_version INTEGER NOT NULL,
        evidence_id UUID,
        allocation_id UUID,
        allocation_version INTEGER,
        id UUID NOT NULL,
        CONSTRAINT pk_cash_flow_events PRIMARY KEY (id),
        CONSTRAINT uq_cash_flow_events_company_id_id UNIQUE (company_id, id),
        CONSTRAINT uq_cash_flow_events_company_id_statement_id_id UNIQUE (company_id,
statement_id, id),
        CONSTRAINT uq_cash_flow_events_statement_id_cash_line_id_counterpa_9f93 UNIQUE
(statement_id, cash_line_id, counterpart_line_id),
        CONSTRAINT fk_cash_flow_events_company_id_statement_id_cash_flow_s_484d FOREIGN
KEY(company_id, statement_id) REFERENCES cash_flow_statements (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_events_company_id_journal_id_journal_entries FOREIGN
KEY(company_id, journal_id) REFERENCES journal_entries (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_cash_flow_events_company_id_cash_account_id_chart_of_ef2c FOREIGN
KEY(company_id, cash_account_id) REFERENCES chart_of_accounts (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_events_company_id_counterpart_account_id_c_71d7 FOREIGN
KEY(company_id, counterpart_account_id) REFERENCES chart_of_accounts (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_events_company_id_classification_id_cash_f_aafd FOREIGN
KEY(company_id, classification_id) REFERENCES cash_flow_classifications (company_id, id) ON
DELETE RESTRICT,
        CONSTRAINT fk_cash_flow_events_company_id_allocation_id_cash_flow__85d7 FOREIGN
KEY(company_id, allocation_id) REFERENCES cash_flow_allocations (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_events_company_id_evidence_id_evidences FOREIGN KEY(company_id,
evidence_id) REFERENCES evidences (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_cash_flow_events_company_id_journal_id_cash_line_id__ef75 FOREIGN
KEY(company_id, journal_id, cash_line_id) REFERENCES journal_lines (company_id,
journal_entry_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_cash_flow_events_company_id_journal_id_counterpart_l_32af FOREIGN
KEY(company_id, journal_id, counterpart_line_id) REFERENCES journal_lines (company_id,
journal_entry_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_cash_flow_events_amount_side CHECK ((cash_inflow > 0 AND cash_outflow = 0)
OR (cash_outflow > 0 AND cash_inflow = 0)),
        CONSTRAINT ck_cash_flow_events_version CHECK (classification_version >= 1),
        CONSTRAINT ck_cash_flow_events_allocation CHECK ((allocation_id IS NULL AND
allocation_version IS NULL) OR (allocation_id IS NOT NULL AND allocation_version IS NOT NULL AND
allocation_version >= 1))
)
""")
    op.execute("""
CREATE TABLE cash_flow_evidence_traces (
        company_id UUID NOT NULL,
        journal_trace_id UUID NOT NULL,
        evidence_id UUID NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_cash_flow_evidence_traces PRIMARY KEY (id),
        CONSTRAINT uq_cash_flow_evidence_traces_journal_trace_id_evidence_id UNIQUE
(journal_trace_id, evidence_id),
        CONSTRAINT fk_cash_flow_evidence_traces_company_id_journal_trace_i_b3d3 FOREIGN
KEY(company_id, journal_trace_id) REFERENCES cash_flow_journal_traces (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_evidence_traces_company_id_evidence_id_evidences FOREIGN
KEY(company_id, evidence_id) REFERENCES evidences (company_id, id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE cash_flow_lines (
        company_id UUID NOT NULL,
        statement_id UUID NOT NULL,
        line_code VARCHAR(60) NOT NULL,
        amount NUMERIC(28, 4) NOT NULL,
        source_type VARCHAR(16) NOT NULL,
        event_id UUID,
        adjustment_id UUID,
        display_order INTEGER NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_cash_flow_lines PRIMARY KEY (id),
        CONSTRAINT uq_cash_flow_lines_company_id_id UNIQUE (company_id, id),
        CONSTRAINT uq_cash_flow_lines_statement_id_display_order UNIQUE (statement_id,
display_order),
        CONSTRAINT fk_cash_flow_lines_company_id_statement_id_cash_flow_statements FOREIGN
KEY(company_id, statement_id) REFERENCES cash_flow_statements (company_id, id) ON DELETE
RESTRICT,
        CONSTRAINT fk_cash_flow_lines_company_id_statement_id_event_id_cas_5867 FOREIGN
KEY(company_id, statement_id, event_id) REFERENCES cash_flow_events (company_id, statement_id,
id) ON DELETE RESTRICT,
        CONSTRAINT fk_cash_flow_lines_company_id_statement_id_adjustment_i_a22d FOREIGN
KEY(company_id, statement_id, adjustment_id) REFERENCES cash_flow_adjustments (company_id,
statement_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_cash_flow_lines_source CHECK ((source_type = 'EVENT' AND event_id IS NOT
NULL AND adjustment_id IS NULL) OR (source_type = 'ADJUSTMENT' AND event_id IS NULL AND
adjustment_id IS NOT NULL) OR (source_type IN ('TOTAL','NET_PROFIT') AND event_id IS NULL AND
adjustment_id IS NULL)),
        CONSTRAINT ck_cash_flow_lines_display_order CHECK (display_order > 0)
)
""")
    for table in (
        "cash_flow_statements",
        "cash_flow_adjustments",
        "cash_flow_balance_sources",
        "cash_flow_commands",
        "cash_flow_journal_traces",
        "cash_flow_adjustment_sources",
        "cash_flow_events",
        "cash_flow_evidence_traces",
        "cash_flow_lines",
    ):
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])
    op.execute("""
CREATE FUNCTION cash_flow_snapshot_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Cash flow snapshot rows are immutable' USING ERRCODE = '23514';
END $$
""")
    op.execute("""
CREATE FUNCTION cash_flow_snapshot_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_transaction bigint;
BEGIN
    IF TG_TABLE_NAME = 'cash_flow_adjustment_sources' THEN
        SELECT s.generation_transaction INTO owner_transaction
        FROM cash_flow_statements s JOIN cash_flow_adjustments a ON a.statement_id = s.id
        WHERE a.id = NEW.adjustment_id AND a.company_id = NEW.company_id;
    ELSIF TG_TABLE_NAME = 'cash_flow_evidence_traces' THEN
        SELECT s.generation_transaction INTO owner_transaction
        FROM cash_flow_statements s JOIN cash_flow_journal_traces j ON j.statement_id = s.id
        WHERE j.id = NEW.journal_trace_id AND j.company_id = NEW.company_id;
    ELSE
        SELECT generation_transaction INTO owner_transaction FROM cash_flow_statements
        WHERE id = NEW.statement_id AND company_id = NEW.company_id;
    END IF;
    IF owner_transaction IS DISTINCT FROM txid_current() THEN
        RAISE EXCEPTION 'Cash flow snapshot generation transaction is sealed'
        USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$
""")
    op.execute(
        "CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON "
        "cash_flow_statements FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
    )
    op.execute(
        "CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON "
        "cash_flow_adjustments FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
    )
    op.execute(
        "CREATE TRIGGER sealed_cash_flow BEFORE INSERT ON cash_flow_adjustments "
        "FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_insert_guard()"
    )
    op.execute(
        "CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON "
        "cash_flow_balance_sources FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
    )
    op.execute(
        "CREATE TRIGGER sealed_cash_flow BEFORE INSERT ON cash_flow_balance_sources "
        "FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_insert_guard()"
    )
    op.execute(
        "CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON "
        "cash_flow_commands FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
    )
    op.execute(
        "CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON "
        "cash_flow_journal_traces FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
    )
    op.execute(
        "CREATE TRIGGER sealed_cash_flow BEFORE INSERT ON cash_flow_journal_traces "
        "FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_insert_guard()"
    )
    op.execute(
        "CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON "
        "cash_flow_adjustment_sources FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
    )
    op.execute(
        "CREATE TRIGGER sealed_cash_flow BEFORE INSERT ON cash_flow_adjustment_sources "
        "FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_insert_guard()"
    )
    op.execute(
        "CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON "
        "cash_flow_events FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
    )
    op.execute(
        "CREATE TRIGGER sealed_cash_flow BEFORE INSERT ON cash_flow_events "
        "FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_insert_guard()"
    )
    op.execute(
        "CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON "
        "cash_flow_evidence_traces FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
    )
    op.execute(
        "CREATE TRIGGER sealed_cash_flow BEFORE INSERT ON cash_flow_evidence_traces "
        "FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_insert_guard()"
    )
    op.execute(
        "CREATE TRIGGER immutable_cash_flow BEFORE UPDATE OR DELETE ON "
        "cash_flow_lines FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_immutable()"
    )
    op.execute(
        "CREATE TRIGGER sealed_cash_flow BEFORE INSERT ON cash_flow_lines "
        "FOR EACH ROW EXECUTE FUNCTION cash_flow_snapshot_insert_guard()"
    )


def downgrade() -> None:
    op.drop_table("cash_flow_lines")
    op.drop_table("cash_flow_evidence_traces")
    op.drop_table("cash_flow_events")
    op.drop_table("cash_flow_adjustment_sources")
    op.drop_table("cash_flow_journal_traces")
    op.drop_table("cash_flow_commands")
    op.drop_table("cash_flow_balance_sources")
    op.drop_table("cash_flow_adjustments")
    op.drop_table("cash_flow_statements")
    op.execute("DROP FUNCTION cash_flow_snapshot_insert_guard()")
    op.execute("DROP FUNCTION cash_flow_snapshot_immutable()")
