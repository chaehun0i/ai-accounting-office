# ruff: noqa: E501
"""Equity classification, verified events and immutable SCE."""

from alembic import op

revision = "031_equity_statement"
down_revision = "030_cash_flow_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE equity_components (
	company_id UUID NOT NULL, 
	component_code VARCHAR(40) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	component_type VARCHAR(32) NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	display_order INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	created_by UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	CONSTRAINT pk_equity_components PRIMARY KEY (id), 
	CONSTRAINT uq_equity_components_company_id_id UNIQUE (company_id, id), 
	CONSTRAINT uq_equity_components_company_id_component_code UNIQUE (company_id, component_code), 
	CONSTRAINT ck_equity_components_type CHECK (component_type IN ('CONTRIBUTED_CAPITAL','RETAINED_EARNINGS','TREASURY_STOCK','OTHER_EQUITY','OCI_COMPONENT')), 
	CONSTRAINT ck_equity_components_state CHECK (status IN ('ACTIVE','INACTIVE') AND display_order > 0 AND version > 0), 
	CONSTRAINT fk_equity_components_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_equity_components_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
)

""")
    op.execute("""
CREATE TABLE equity_account_mappings (
	company_id UUID NOT NULL, 
	component_id UUID NOT NULL, 
	account_id UUID NOT NULL, 
	effective_from DATE NOT NULL, 
	effective_to DATE, 
	status VARCHAR(12) NOT NULL, 
	version INTEGER NOT NULL, 
	created_by UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	CONSTRAINT pk_equity_account_mappings PRIMARY KEY (id), 
	CONSTRAINT uq_equity_account_mappings_company_id_id UNIQUE (company_id, id), 
	CONSTRAINT uq_equity_account_mappings_company_id_account_id_version UNIQUE (company_id, account_id, version), 
	CONSTRAINT fk_equity_account_mappings_company_id_component_id_equi_fd8b FOREIGN KEY(company_id, component_id) REFERENCES equity_components (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_equity_account_mappings_company_id_account_id_chart__2a9c FOREIGN KEY(company_id, account_id) REFERENCES chart_of_accounts (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_equity_account_mappings_dates CHECK (effective_to IS NULL OR effective_to >= effective_from), 
	CONSTRAINT ck_equity_account_mappings_state CHECK (status IN ('ACTIVE','INACTIVE') AND version > 0), 
	CONSTRAINT fk_equity_account_mappings_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_equity_account_mappings_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
)

""")
    op.execute("""
CREATE TABLE equity_events (
	company_id UUID NOT NULL, 
	component_id UUID NOT NULL, 
	event_date DATE NOT NULL, 
	event_type VARCHAR(32) NOT NULL, 
	amount NUMERIC(19, 4) NOT NULL, 
	source_journal_id UUID NOT NULL, 
	source_journal_line_id UUID NOT NULL, 
	approval_id UUID NOT NULL, 
	mapping_version INTEGER NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	created_by UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	CONSTRAINT pk_equity_events PRIMARY KEY (id), 
	CONSTRAINT uq_equity_events_company_id_id UNIQUE (company_id, id), 
	CONSTRAINT uq_equity_events_company_id_source_journal_line_id UNIQUE (company_id, source_journal_line_id), 
	CONSTRAINT fk_equity_events_company_id_component_id_equity_components FOREIGN KEY(company_id, component_id) REFERENCES equity_components (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_equity_events_company_id_source_journal_id_source_jo_ab8c FOREIGN KEY(company_id, source_journal_id, source_journal_line_id) REFERENCES journal_lines (company_id, journal_entry_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_equity_events_company_id_approval_id_approvals FOREIGN KEY(company_id, approval_id) REFERENCES approvals (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_equity_events_type CHECK (event_type IN ('CAPITAL_CONTRIBUTION','CAPITAL_REDUCTION','DIVIDEND','TREASURY_STOCK_ACQUIRE','TREASURY_STOCK_DISPOSE','PROFIT_TRANSFER','OCI_TRANSFER','OTHER_ADJUSTMENT')), 
	CONSTRAINT ck_equity_events_state CHECK (status = 'VERIFIED' AND mapping_version > 0), 
	CONSTRAINT fk_equity_events_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_equity_events_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
)

""")
    op.execute("""
CREATE TABLE dividend_declarations (
	company_id UUID NOT NULL, 
	resolution_date DATE NOT NULL, 
	payable_date DATE, 
	total_amount NUMERIC(19, 4) NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	approval_id UUID, 
	source_journal_id UUID, 
	created_by UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	CONSTRAINT pk_dividend_declarations PRIMARY KEY (id), 
	CONSTRAINT uq_dividend_declarations_company_id_id UNIQUE (company_id, id), 
	CONSTRAINT fk_dividend_declarations_company_id_approval_id_approvals FOREIGN KEY(company_id, approval_id) REFERENCES approvals (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_dividend_declarations_company_id_source_journal_id_j_a0f2 FOREIGN KEY(company_id, source_journal_id) REFERENCES journal_entries (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_dividend_declarations_amount_dates CHECK (total_amount > 0 AND (payable_date IS NULL OR payable_date >= resolution_date)), 
	CONSTRAINT ck_dividend_declarations_status CHECK (status IN ('PROPOSED','APPROVED','CANCELLED')), 
	CONSTRAINT ck_dividend_declarations_approved_source CHECK (status <> 'APPROVED' OR (approval_id IS NOT NULL AND source_journal_id IS NOT NULL)), 
	CONSTRAINT fk_dividend_declarations_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_dividend_declarations_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
)

""")
    op.execute("""
CREATE TABLE statement_of_changes_in_equity (
	company_id UUID NOT NULL, 
	statement_set_id UUID NOT NULL, 
	period_id UUID NOT NULL, 
	close_version INTEGER NOT NULL, 
	balance_sheet_digest VARCHAR(64) NOT NULL, 
	income_statement_digest VARCHAR(64) NOT NULL, 
	mapping_digest VARCHAR(64) NOT NULL, 
	event_digest VARCHAR(64) NOT NULL, 
	source_digest VARCHAR(64) NOT NULL, 
	snapshot_digest VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	generated_by UUID NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	generation_transaction BIGINT DEFAULT txid_current() NOT NULL,
	id UUID NOT NULL, 
	CONSTRAINT pk_statement_of_changes_in_equity PRIMARY KEY (id), 
	CONSTRAINT uq_statement_of_changes_in_equity_company_id_id UNIQUE (company_id, id), 
	CONSTRAINT uq_statement_of_changes_in_equity_company_id_period_id__ec15 UNIQUE (company_id, period_id, snapshot_digest), 
	CONSTRAINT fk_statement_of_changes_in_equity_company_id_statement__1d56 FOREIGN KEY(company_id, statement_set_id) REFERENCES financial_statement_sets (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_statement_of_changes_in_equity_company_id_period_id__2544 FOREIGN KEY(company_id, period_id) REFERENCES accounting_periods (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_statement_of_changes_in_equity_status CHECK (status = 'RECONCILED' AND close_version > 0), 
	CONSTRAINT fk_statement_of_changes_in_equity_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_statement_of_changes_in_equity_generated_by_users FOREIGN KEY(generated_by) REFERENCES users (id) ON DELETE RESTRICT
)

""")
    op.execute("""
CREATE TABLE equity_statement_lines (
	company_id UUID NOT NULL, 
	statement_id UUID NOT NULL, 
	component_id UUID NOT NULL, 
	movement_type VARCHAR(32) NOT NULL, 
	amount NUMERIC(19, 4) NOT NULL, 
	display_order INTEGER NOT NULL, 
	id UUID NOT NULL, 
	CONSTRAINT pk_equity_statement_lines PRIMARY KEY (id), 
	CONSTRAINT uq_equity_statement_lines_company_id_id UNIQUE (company_id, id), 
	CONSTRAINT uq_equity_statement_lines_company_id_statement_id_compo_866e UNIQUE (company_id, statement_id, component_id, movement_type), 
	CONSTRAINT fk_equity_statement_lines_company_id_statement_id_state_80c5 FOREIGN KEY(company_id, statement_id) REFERENCES statement_of_changes_in_equity (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_equity_statement_lines_company_id_component_id_equit_7a63 FOREIGN KEY(company_id, component_id) REFERENCES equity_components (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_equity_statement_lines_movement CHECK (movement_type IN ('OPENING','OWNER_TRANSACTIONS','PROFIT_OR_LOSS','OTHER_COMPREHENSIVE_INCOME','OTHER_ADJUSTMENTS','CLOSING')), 
	CONSTRAINT fk_equity_statement_lines_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT
)

""")
    op.execute("""
CREATE TABLE equity_statement_sources (
	company_id UUID NOT NULL, 
	statement_line_id UUID NOT NULL, 
	journal_line_id UUID, 
	income_statement_id UUID, 
	amount NUMERIC(19, 4) NOT NULL, 
	id UUID NOT NULL, 
	CONSTRAINT pk_equity_statement_sources PRIMARY KEY (id), 
	CONSTRAINT fk_equity_statement_sources_company_id_statement_line_i_3c7a FOREIGN KEY(company_id, statement_line_id) REFERENCES equity_statement_lines (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_equity_statement_sources_company_id_journal_line_id__f87d FOREIGN KEY(company_id, journal_line_id) REFERENCES journal_lines (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_equity_statement_sources_company_id_income_statement_f32d FOREIGN KEY(company_id, income_statement_id) REFERENCES financial_statements (company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_equity_statement_sources_one_source CHECK ((journal_line_id IS NULL) <> (income_statement_id IS NULL)), 
	CONSTRAINT fk_equity_statement_sources_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT
)

""")
    op.execute("""
CREATE TABLE equity_statement_commands (
    company_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    statement_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    id UUID NOT NULL,
    CONSTRAINT pk_equity_statement_commands PRIMARY KEY (id),
    CONSTRAINT uq_equity_statement_commands_company_id_actor_id_idempo_136f
        UNIQUE (company_id, actor_id, idempotency_key),
    CONSTRAINT fk_equity_statement_commands_company
        FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE RESTRICT,
    CONSTRAINT fk_equity_statement_commands_actor
        FOREIGN KEY (actor_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT fk_equity_statement_commands_statement
        FOREIGN KEY (company_id, statement_id)
        REFERENCES statement_of_changes_in_equity (company_id, id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE dividend_payments (
    company_id UUID NOT NULL,
    declaration_id UUID NOT NULL,
    cash_flow_statement_id UUID NOT NULL,
    cash_flow_event_id UUID NOT NULL,
    journal_id UUID NOT NULL,
    payment_date DATE NOT NULL,
    amount NUMERIC(19, 4) NOT NULL,
    created_by UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    id UUID NOT NULL,
    CONSTRAINT pk_dividend_payments PRIMARY KEY (id),
    CONSTRAINT uq_dividend_payments_company_id_id UNIQUE (company_id, id),
    CONSTRAINT uq_dividend_payments_company_id_cash_flow_event_id
        UNIQUE (company_id, cash_flow_event_id),
    CONSTRAINT fk_dividend_payments_company FOREIGN KEY (company_id)
        REFERENCES companies (id) ON DELETE RESTRICT,
    CONSTRAINT fk_dividend_payments_declaration FOREIGN KEY (company_id, declaration_id)
        REFERENCES dividend_declarations (company_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_dividend_payments_cash_event
        FOREIGN KEY (company_id, cash_flow_statement_id, cash_flow_event_id)
        REFERENCES cash_flow_events (company_id, statement_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_dividend_payments_journal FOREIGN KEY (company_id, journal_id)
        REFERENCES journal_entries (company_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_dividend_payments_creator FOREIGN KEY (created_by)
        REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT ck_dividend_payments_amount CHECK (amount > 0)
)
""")
    op.execute("""
CREATE FUNCTION equity_snapshot_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Equity snapshot rows are immutable' USING ERRCODE = '23514';
END
$$
""")
    op.execute("""
CREATE FUNCTION equity_snapshot_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_transaction BIGINT;
BEGIN
    IF TG_TABLE_NAME = 'equity_statement_lines' THEN
        SELECT generation_transaction INTO parent_transaction
        FROM statement_of_changes_in_equity
        WHERE company_id = NEW.company_id AND id = NEW.statement_id;
    ELSE
        SELECT statement.generation_transaction INTO parent_transaction
        FROM equity_statement_lines AS line
        JOIN statement_of_changes_in_equity AS statement
          ON statement.company_id = line.company_id AND statement.id = line.statement_id
        WHERE line.company_id = NEW.company_id AND line.id = NEW.statement_line_id;
    END IF;
    IF parent_transaction IS NULL OR parent_transaction <> txid_current() THEN
        RAISE EXCEPTION 'Equity snapshot is sealed' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$
""")
    for table in (
        "statement_of_changes_in_equity", "equity_statement_lines",
        "equity_statement_sources", "equity_statement_commands",
    ):
        op.execute(
            f"CREATE TRIGGER immutable_equity BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION equity_snapshot_immutable()"
        )
    for table in ("equity_statement_lines", "equity_statement_sources"):
        op.execute(
            f"CREATE TRIGGER sealed_equity BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION equity_snapshot_insert_guard()"
        )


def downgrade() -> None:
    for table in (
        "statement_of_changes_in_equity", "equity_statement_lines",
        "equity_statement_sources", "equity_statement_commands",
    ):
        op.execute(f"DROP TRIGGER immutable_equity ON {table}")
    for table in ("equity_statement_lines", "equity_statement_sources"):
        op.execute(f"DROP TRIGGER sealed_equity ON {table}")
    op.execute("DROP FUNCTION equity_snapshot_insert_guard()")
    op.execute("DROP FUNCTION equity_snapshot_immutable()")
    op.drop_table("dividend_payments")
    op.drop_table("equity_statement_commands")
    op.drop_table("equity_statement_sources")
    op.drop_table("equity_statement_lines")
    op.drop_table("statement_of_changes_in_equity")
    op.drop_table("dividend_declarations")
    op.drop_table("equity_events")
    op.drop_table("equity_account_mappings")
    op.drop_table("equity_components")
