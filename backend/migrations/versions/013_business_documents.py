"""매출·매입 문서와 정정 사실을 순방향으로 추가합니다."""

import sqlalchemy as sa
from alembic import op

revision = "013_business_documents"
down_revision = "012_import_transaction_promotion"
branch_labels = None
depends_on = None

DDL = {
    "sales_invoices": [
        """
        CREATE TABLE sales_invoices (
        company_id UUID NOT NULL,
        document_no VARCHAR(100) NOT NULL,
        counterparty_id UUID NOT NULL,
        issue_date DATE NOT NULL,
        accounting_date DATE NOT NULL,
        due_date DATE NOT NULL,
        currency_code VARCHAR(3) NOT NULL,
        supply_amount NUMERIC(19, 4) NOT NULL,
        tax_amount NUMERIC(19, 4) NOT NULL,
        total_amount NUMERIC(19, 4) NOT NULL,
        status VARCHAR(30) NOT NULL,
        source_system VARCHAR(80) NOT NULL,
        source_id VARCHAR(100) NOT NULL,
        source_fingerprint VARCHAR(64) NOT NULL,
        source_import_id UUID,
        evidence_id UUID,
        transaction_id UUID,
        created_by UUID NOT NULL,
        approved_by UUID,
        approved_at TIMESTAMP WITH TIME ZONE,
        id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_sales_invoices PRIMARY KEY (id),
        CONSTRAINT uq_sales_invoices_company_id_id UNIQUE (company_id, id),
        CONSTRAINT uq_sales_invoices_company_id_document_no UNIQUE (company_id, document_no),
        CONSTRAINT uq_sales_invoices_company_id_source_system_source_id UNIQUE (company_id,
        source_system, source_id),
        CONSTRAINT uq_sales_invoices_company_id_transaction_id UNIQUE (company_id,
        transaction_id),
        CONSTRAINT fk_sales_invoices_company_id_counterparty_id_counterparties FOREIGN
        KEY(company_id, counterparty_id) REFERENCES counterparties (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT fk_sales_invoices_company_id_source_import_id_imports FOREIGN KEY(company_id,
        source_import_id) REFERENCES imports (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_sales_invoices_company_id_evidence_id_evidences FOREIGN KEY(company_id,
        evidence_id) REFERENCES evidences (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_sales_invoices_company_id_transaction_id_transactions FOREIGN
        KEY(company_id, transaction_id) REFERENCES transactions (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT ck_sales_invoices_currency CHECK (currency_code='KRW'),
        CONSTRAINT ck_sales_invoices_version CHECK (version >= 1),
        CONSTRAINT ck_sales_invoices_dates CHECK (due_date >= issue_date),
        CONSTRAINT ck_sales_invoices_amount CHECK (supply_amount >= 0 AND tax_amount >= 0 AND
        total_amount > 0 AND total_amount = supply_amount + tax_amount AND total_amount <
        1000000000000000),
        CONSTRAINT ck_sales_invoices_status CHECK (status IN
        ('DRAFT','REVIEW_REQUIRED','APPROVED','APPLIED')),
        CONSTRAINT ck_sales_invoices_approval CHECK ((status IN ('DRAFT','REVIEW_REQUIRED') AND
        transaction_id IS NULL AND approved_by IS NULL AND approved_at IS NULL) OR (status IN
        ('APPROVED','APPLIED') AND transaction_id IS NOT NULL AND approved_by IS NOT NULL AND
        approved_at IS NOT NULL AND approved_by <> created_by)),
        CONSTRAINT fk_sales_invoices_company_id_companies FOREIGN KEY(company_id) REFERENCES
        companies (id) ON DELETE RESTRICT,
        CONSTRAINT fk_sales_invoices_created_by_users FOREIGN KEY(created_by) REFERENCES users
        (id) ON DELETE RESTRICT,
        CONSTRAINT fk_sales_invoices_approved_by_users FOREIGN KEY(approved_by) REFERENCES users
        (id) ON DELETE RESTRICT
        )
        """,
        """
        CREATE INDEX ix_sales_invoices_approved_by ON sales_invoices (approved_by)
        """,
        """
        CREATE INDEX ix_sales_invoices_company_id ON sales_invoices (company_id)
        """,
        """
        CREATE INDEX ix_sales_invoices_counterparty_id ON sales_invoices (counterparty_id)
        """,
        """
        CREATE INDEX ix_sales_invoices_created_by ON sales_invoices (created_by)
        """,
        """
        CREATE INDEX ix_sales_invoices_evidence_id ON sales_invoices (evidence_id)
        """,
        """
        CREATE INDEX ix_sales_invoices_issue_date ON sales_invoices (issue_date)
        """,
        """
        CREATE INDEX ix_sales_invoices_source_import_id ON sales_invoices (source_import_id)
        """,
        """
        CREATE INDEX ix_sales_invoices_transaction_id ON sales_invoices (transaction_id)
        """,
    ],
    "purchase_invoices": [
        """
        CREATE TABLE purchase_invoices (
        company_id UUID NOT NULL,
        document_no VARCHAR(100) NOT NULL,
        counterparty_id UUID NOT NULL,
        issue_date DATE NOT NULL,
        accounting_date DATE NOT NULL,
        due_date DATE NOT NULL,
        currency_code VARCHAR(3) NOT NULL,
        supply_amount NUMERIC(19, 4) NOT NULL,
        tax_amount NUMERIC(19, 4) NOT NULL,
        total_amount NUMERIC(19, 4) NOT NULL,
        status VARCHAR(30) NOT NULL,
        source_system VARCHAR(80) NOT NULL,
        source_id VARCHAR(100) NOT NULL,
        source_fingerprint VARCHAR(64) NOT NULL,
        source_import_id UUID,
        evidence_id UUID,
        transaction_id UUID,
        created_by UUID NOT NULL,
        approved_by UUID,
        approved_at TIMESTAMP WITH TIME ZONE,
        id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_purchase_invoices PRIMARY KEY (id),
        CONSTRAINT uq_purchase_invoices_company_id_id UNIQUE (company_id, id),
        CONSTRAINT uq_purchase_invoices_company_id_document_no UNIQUE (company_id, document_no),
        CONSTRAINT uq_purchase_invoices_company_id_source_system_source_id UNIQUE (company_id,
        source_system, source_id),
        CONSTRAINT uq_purchase_invoices_company_id_transaction_id UNIQUE (company_id,
        transaction_id),
        CONSTRAINT fk_purchase_invoices_company_id_counterparty_id_counterparties FOREIGN
        KEY(company_id, counterparty_id) REFERENCES counterparties (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT fk_purchase_invoices_company_id_source_import_id_imports FOREIGN
        KEY(company_id, source_import_id) REFERENCES imports (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_purchase_invoices_company_id_evidence_id_evidences FOREIGN KEY(company_id,
        evidence_id) REFERENCES evidences (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_purchase_invoices_company_id_transaction_id_transactions FOREIGN
        KEY(company_id, transaction_id) REFERENCES transactions (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT ck_purchase_invoices_currency CHECK (currency_code='KRW'),
        CONSTRAINT ck_purchase_invoices_version CHECK (version >= 1),
        CONSTRAINT ck_purchase_invoices_dates CHECK (due_date >= issue_date),
        CONSTRAINT ck_purchase_invoices_amount CHECK (supply_amount >= 0 AND tax_amount >= 0 AND
        total_amount > 0 AND total_amount = supply_amount + tax_amount AND total_amount <
        1000000000000000),
        CONSTRAINT ck_purchase_invoices_status CHECK (status IN
        ('DRAFT','REVIEW_REQUIRED','APPROVED','APPLIED')),
        CONSTRAINT ck_purchase_invoices_approval CHECK ((status IN ('DRAFT','REVIEW_REQUIRED') AND
        transaction_id IS NULL AND approved_by IS NULL AND approved_at IS NULL) OR (status IN
        ('APPROVED','APPLIED') AND transaction_id IS NOT NULL AND approved_by IS NOT NULL AND
        approved_at IS NOT NULL AND approved_by <> created_by)),
        CONSTRAINT fk_purchase_invoices_company_id_companies FOREIGN KEY(company_id) REFERENCES
        companies (id) ON DELETE RESTRICT,
        CONSTRAINT fk_purchase_invoices_created_by_users FOREIGN KEY(created_by) REFERENCES users
        (id) ON DELETE RESTRICT,
        CONSTRAINT fk_purchase_invoices_approved_by_users FOREIGN KEY(approved_by) REFERENCES
        users (id) ON DELETE RESTRICT
        )
        """,
        """
        CREATE INDEX ix_purchase_invoices_approved_by ON purchase_invoices (approved_by)
        """,
        """
        CREATE INDEX ix_purchase_invoices_company_id ON purchase_invoices (company_id)
        """,
        """
        CREATE INDEX ix_purchase_invoices_counterparty_id ON purchase_invoices (counterparty_id)
        """,
        """
        CREATE INDEX ix_purchase_invoices_created_by ON purchase_invoices (created_by)
        """,
        """
        CREATE INDEX ix_purchase_invoices_evidence_id ON purchase_invoices (evidence_id)
        """,
        """
        CREATE INDEX ix_purchase_invoices_issue_date ON purchase_invoices (issue_date)
        """,
        """
        CREATE INDEX ix_purchase_invoices_source_import_id ON purchase_invoices (source_import_id)
        """,
        """
        CREATE INDEX ix_purchase_invoices_transaction_id ON purchase_invoices (transaction_id)
        """,
    ],
    "document_notes": [
        """
        CREATE TABLE document_notes (
        note_type VARCHAR(20) NOT NULL,
        sales_invoice_id UUID,
        purchase_invoice_id UUID,
        reason_code VARCHAR(100) NOT NULL,
        original_version INTEGER NOT NULL,
        company_id UUID NOT NULL,
        document_no VARCHAR(100) NOT NULL,
        counterparty_id UUID NOT NULL,
        issue_date DATE NOT NULL,
        accounting_date DATE NOT NULL,
        due_date DATE NOT NULL,
        currency_code VARCHAR(3) NOT NULL,
        supply_amount NUMERIC(19, 4) NOT NULL,
        tax_amount NUMERIC(19, 4) NOT NULL,
        total_amount NUMERIC(19, 4) NOT NULL,
        status VARCHAR(30) NOT NULL,
        source_system VARCHAR(80) NOT NULL,
        source_id VARCHAR(100) NOT NULL,
        source_fingerprint VARCHAR(64) NOT NULL,
        source_import_id UUID,
        evidence_id UUID,
        transaction_id UUID,
        created_by UUID NOT NULL,
        approved_by UUID,
        approved_at TIMESTAMP WITH TIME ZONE,
        id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_document_notes PRIMARY KEY (id),
        CONSTRAINT uq_document_notes_company_id_id UNIQUE (company_id, id),
        CONSTRAINT uq_document_notes_company_id_document_no UNIQUE (company_id, document_no),
        CONSTRAINT uq_document_notes_company_id_source_system_source_id UNIQUE (company_id,
        source_system, source_id),
        CONSTRAINT uq_document_notes_company_id_transaction_id UNIQUE (company_id,
        transaction_id),
        CONSTRAINT fk_document_notes_company_id_counterparty_id_counterparties FOREIGN
        KEY(company_id, counterparty_id) REFERENCES counterparties (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT fk_document_notes_company_id_source_import_id_imports FOREIGN KEY(company_id,
        source_import_id) REFERENCES imports (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_document_notes_company_id_evidence_id_evidences FOREIGN KEY(company_id,
        evidence_id) REFERENCES evidences (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_document_notes_company_id_transaction_id_transactions FOREIGN
        KEY(company_id, transaction_id) REFERENCES transactions (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT ck_document_notes_currency CHECK (currency_code='KRW'),
        CONSTRAINT ck_document_notes_version CHECK (version >= 1),
        CONSTRAINT ck_document_notes_dates CHECK (due_date >= issue_date),
        CONSTRAINT ck_document_notes_amount CHECK (supply_amount >= 0 AND tax_amount >= 0 AND
        total_amount > 0 AND total_amount = supply_amount + tax_amount AND total_amount <
        1000000000000000),
        CONSTRAINT ck_document_notes_status CHECK (status IN
        ('DRAFT','REVIEW_REQUIRED','APPROVED','APPLIED')),
        CONSTRAINT ck_document_notes_approval CHECK ((status IN ('DRAFT','REVIEW_REQUIRED') AND
        transaction_id IS NULL AND approved_by IS NULL AND approved_at IS NULL) OR (status IN
        ('APPROVED','APPLIED') AND transaction_id IS NOT NULL AND approved_by IS NOT NULL AND
        approved_at IS NOT NULL AND approved_by <> created_by)),
        CONSTRAINT fk_document_notes_company_id_sales_invoice_id_sales_invoices FOREIGN
        KEY(company_id, sales_invoice_id) REFERENCES sales_invoices (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT fk_document_notes_company_id_purchase_invoice_id_purcha_6279 FOREIGN
        KEY(company_id, purchase_invoice_id) REFERENCES purchase_invoices (company_id, id) ON
        DELETE RESTRICT,
        CONSTRAINT ck_document_notes_note_type CHECK (note_type IN ('CREDIT_NOTE','DEBIT_NOTE')),
        CONSTRAINT ck_document_notes_original CHECK
        (num_nonnulls(sales_invoice_id,purchase_invoice_id)=1),
        CONSTRAINT ck_document_notes_original_version CHECK (original_version >= 1),
        CONSTRAINT fk_document_notes_company_id_companies FOREIGN KEY(company_id) REFERENCES
        companies (id) ON DELETE RESTRICT,
        CONSTRAINT fk_document_notes_created_by_users FOREIGN KEY(created_by) REFERENCES users
        (id) ON DELETE RESTRICT,
        CONSTRAINT fk_document_notes_approved_by_users FOREIGN KEY(approved_by) REFERENCES users
        (id) ON DELETE RESTRICT
        )
        """,
        """
        CREATE INDEX ix_document_notes_approved_by ON document_notes (approved_by)
        """,
        """
        CREATE INDEX ix_document_notes_company_id ON document_notes (company_id)
        """,
        """
        CREATE INDEX ix_document_notes_counterparty_id ON document_notes (counterparty_id)
        """,
        """
        CREATE INDEX ix_document_notes_created_by ON document_notes (created_by)
        """,
        """
        CREATE INDEX ix_document_notes_evidence_id ON document_notes (evidence_id)
        """,
        """
        CREATE INDEX ix_document_notes_issue_date ON document_notes (issue_date)
        """,
        """
        CREATE INDEX ix_document_notes_purchase_invoice_id ON document_notes (purchase_invoice_id)
        """,
        """
        CREATE INDEX ix_document_notes_sales_invoice_id ON document_notes (sales_invoice_id)
        """,
        """
        CREATE INDEX ix_document_notes_source_import_id ON document_notes (source_import_id)
        """,
        """
        CREATE INDEX ix_document_notes_transaction_id ON document_notes (transaction_id)
        """,
    ],
    "sales_invoice_lines": [
        """
        CREATE TABLE sales_invoice_lines (
        company_id UUID NOT NULL,
        invoice_id UUID NOT NULL,
        line_no INTEGER NOT NULL,
        description VARCHAR(500) NOT NULL,
        quantity NUMERIC(19, 4),
        unit_price NUMERIC(19, 4),
        supply_amount NUMERIC(19, 4) NOT NULL,
        tax_amount NUMERIC(19, 4) NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_sales_invoice_lines PRIMARY KEY (id),
        CONSTRAINT uq_sales_invoice_lines_invoice_id_line_no UNIQUE (invoice_id, line_no),
        CONSTRAINT fk_sales_invoice_lines_company_id_invoice_id_sales_invoices FOREIGN
        KEY(company_id, invoice_id) REFERENCES sales_invoices (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_sales_invoice_lines_line_no CHECK (line_no >= 1),
        CONSTRAINT ck_sales_invoice_lines_amount CHECK (supply_amount >= 0 AND tax_amount >= 0 AND
        supply_amount + tax_amount > 0 AND supply_amount + tax_amount < 1000000000000000),
        CONSTRAINT ck_sales_invoice_lines_quantity CHECK ((quantity IS NULL AND unit_price IS
        NULL) OR (quantity IS NOT NULL AND unit_price IS NOT NULL AND quantity > 0 AND unit_price
        >= 0 AND quantity * unit_price = supply_amount))
        )
        """,
        """
        CREATE INDEX ix_sales_invoice_lines_company_id ON sales_invoice_lines (company_id)
        """,
        """
        CREATE INDEX ix_sales_invoice_lines_invoice_id ON sales_invoice_lines (invoice_id)
        """,
    ],
    "purchase_invoice_lines": [
        """
        CREATE TABLE purchase_invoice_lines (
        company_id UUID NOT NULL,
        invoice_id UUID NOT NULL,
        line_no INTEGER NOT NULL,
        description VARCHAR(500) NOT NULL,
        quantity NUMERIC(19, 4),
        unit_price NUMERIC(19, 4),
        supply_amount NUMERIC(19, 4) NOT NULL,
        tax_amount NUMERIC(19, 4) NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_purchase_invoice_lines PRIMARY KEY (id),
        CONSTRAINT uq_purchase_invoice_lines_invoice_id_line_no UNIQUE (invoice_id, line_no),
        CONSTRAINT fk_purchase_invoice_lines_company_id_invoice_id_purchas_64e7 FOREIGN
        KEY(company_id, invoice_id) REFERENCES purchase_invoices (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT ck_purchase_invoice_lines_line_no CHECK (line_no >= 1),
        CONSTRAINT ck_purchase_invoice_lines_amount CHECK (supply_amount >= 0 AND tax_amount >= 0
        AND supply_amount + tax_amount > 0 AND supply_amount + tax_amount < 1000000000000000),
        CONSTRAINT ck_purchase_invoice_lines_quantity CHECK ((quantity IS NULL AND unit_price IS
        NULL) OR (quantity IS NOT NULL AND unit_price IS NOT NULL AND quantity > 0 AND unit_price
        >= 0 AND quantity * unit_price = supply_amount))
        )
        """,
        """
        CREATE INDEX ix_purchase_invoice_lines_company_id ON purchase_invoice_lines (company_id)
        """,
        """
        CREATE INDEX ix_purchase_invoice_lines_invoice_id ON purchase_invoice_lines (invoice_id)
        """,
    ],
    "document_note_lines": [
        """
        CREATE TABLE document_note_lines (
        company_id UUID NOT NULL,
        invoice_id UUID NOT NULL,
        line_no INTEGER NOT NULL,
        description VARCHAR(500) NOT NULL,
        quantity NUMERIC(19, 4),
        unit_price NUMERIC(19, 4),
        supply_amount NUMERIC(19, 4) NOT NULL,
        tax_amount NUMERIC(19, 4) NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_document_note_lines PRIMARY KEY (id),
        CONSTRAINT uq_document_note_lines_invoice_id_line_no UNIQUE (invoice_id, line_no),
        CONSTRAINT fk_document_note_lines_company_id_invoice_id_document_notes FOREIGN
        KEY(company_id, invoice_id) REFERENCES document_notes (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_document_note_lines_line_no CHECK (line_no >= 1),
        CONSTRAINT ck_document_note_lines_amount CHECK (supply_amount >= 0 AND tax_amount >= 0 AND
        supply_amount + tax_amount > 0 AND supply_amount + tax_amount < 1000000000000000),
        CONSTRAINT ck_document_note_lines_quantity CHECK ((quantity IS NULL AND unit_price IS
        NULL) OR (quantity IS NOT NULL AND unit_price IS NOT NULL AND quantity > 0 AND unit_price
        >= 0 AND quantity * unit_price = supply_amount))
        )
        """,
        """
        CREATE INDEX ix_document_note_lines_company_id ON document_note_lines (company_id)
        """,
        """
        CREATE INDEX ix_document_note_lines_invoice_id ON document_note_lines (invoice_id)
        """,
    ],
    "business_document_events": [
        """
        CREATE TABLE business_document_events (
        company_id UUID NOT NULL,
        actor_id UUID NOT NULL,
        sales_invoice_id UUID,
        purchase_invoice_id UUID,
        document_note_id UUID,
        command_code VARCHAR(40) NOT NULL,
        idempotency_key VARCHAR(100) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL,
        before_status VARCHAR(30) NOT NULL,
        after_status VARCHAR(30) NOT NULL,
        result_version INTEGER NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_business_document_events PRIMARY KEY (id),
        CONSTRAINT uq_business_document_events_company_id_actor_id_command_89d6 UNIQUE
        (company_id, actor_id, command_code, idempotency_key),
        CONSTRAINT fk_business_document_events_company_id_sales_invoice_id_e24a FOREIGN
        KEY(company_id, sales_invoice_id) REFERENCES sales_invoices (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT fk_business_document_events_company_id_purchase_invoice_a0fe FOREIGN
        KEY(company_id, purchase_invoice_id) REFERENCES purchase_invoices (company_id, id) ON
        DELETE RESTRICT,
        CONSTRAINT fk_business_document_events_company_id_document_note_id_c218 FOREIGN
        KEY(company_id, document_note_id) REFERENCES document_notes (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT ck_business_document_events_resource CHECK
        (num_nonnulls(sales_invoice_id,purchase_invoice_id,document_note_id)=1),
        CONSTRAINT ck_business_document_events_version CHECK (result_version >= 1),
        CONSTRAINT fk_business_document_events_company_id_companies FOREIGN KEY(company_id)
        REFERENCES companies (id) ON DELETE RESTRICT,
        CONSTRAINT fk_business_document_events_actor_id_users FOREIGN KEY(actor_id) REFERENCES
        users (id) ON DELETE RESTRICT
        )
        """,
        """
        CREATE INDEX ix_business_document_events_actor_id ON business_document_events (actor_id)
        """,
        """
        CREATE INDEX ix_business_document_events_company_id ON business_document_events
        (company_id)
        """,
        """
        CREATE INDEX ix_business_document_events_document_note_id ON business_document_events
        (document_note_id)
        """,
        """
        CREATE INDEX ix_business_document_events_purchase_invoice_id ON business_document_events
        (purchase_invoice_id)
        """,
        """
        CREATE INDEX ix_business_document_events_sales_invoice_id ON business_document_events
        (sales_invoice_id)
        """,
    ],
    "obligation_adjustments": [
        """
        CREATE TABLE obligation_adjustments (
        company_id UUID NOT NULL,
        document_note_id UUID NOT NULL,
        receivable_id UUID,
        payable_id UUID,
        adjustment_type VARCHAR(20) NOT NULL,
        amount NUMERIC(19, 4) NOT NULL,
        effective_date DATE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        id UUID NOT NULL,
        CONSTRAINT pk_obligation_adjustments PRIMARY KEY (id),
        CONSTRAINT uq_obligation_adjustments_company_id_document_note_id UNIQUE (company_id,
        document_note_id),
        CONSTRAINT fk_obligation_adjustments_company_id_document_note_id_d_f64a FOREIGN
        KEY(company_id, document_note_id) REFERENCES document_notes (company_id, id) ON DELETE
        RESTRICT,
        CONSTRAINT fk_obligation_adjustments_company_id_receivable_id_receivables FOREIGN
        KEY(company_id, receivable_id) REFERENCES receivables (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT fk_obligation_adjustments_company_id_payable_id_payables FOREIGN
        KEY(company_id, payable_id) REFERENCES payables (company_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_obligation_adjustments_target CHECK
        (num_nonnulls(receivable_id,payable_id)=1),
        CONSTRAINT ck_obligation_adjustments_type CHECK (adjustment_type IN
        ('CREDIT_NOTE','DEBIT_NOTE')),
        CONSTRAINT ck_obligation_adjustments_amount CHECK (amount > 0 AND amount <
        1000000000000000),
        CONSTRAINT fk_obligation_adjustments_company_id_companies FOREIGN KEY(company_id)
        REFERENCES companies (id) ON DELETE RESTRICT
        )
        """,
        """
        CREATE INDEX ix_obligation_adjustments_company_id ON obligation_adjustments (company_id)
        """,
        """
        CREATE INDEX ix_obligation_adjustments_document_note_id ON obligation_adjustments
        (document_note_id)
        """,
        """
        CREATE INDEX ix_obligation_adjustments_payable_id ON obligation_adjustments (payable_id)
        """,
        """
        CREATE INDEX ix_obligation_adjustments_receivable_id ON obligation_adjustments
        (receivable_id)
        """,
    ],
}


def upgrade() -> None:
    for name, statements in DDL.items():
        if name == "obligation_adjustments":
            continue
        for statement in statements:
            op.execute(statement)
    for table, invoice in [("receivables", "sales_invoices"), ("payables", "purchase_invoices")]:
        op.alter_column(table, "origin_journal_id", nullable=True)
        op.alter_column(table, "origin_line_no", nullable=True)
        for column in ["source_transaction_id", "source_invoice_id"]:
            op.add_column(table, sa.Column(column, sa.Uuid(), nullable=True))
            op.create_index(op.f(f"ix_{table}_{column}"), table, [column])
            op.create_unique_constraint(
                op.f(f"uq_{table}_company_id_{column}"), table, ["company_id", column]
            )
        op.add_column(table, sa.Column("recognized_date", sa.Date(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_company_id_source_invoice_id_{invoice}"),
            table,
            invoice,
            ["company_id", "source_invoice_id"],
            ["company_id", "id"],
            ondelete="RESTRICT",
        )
        op.create_foreign_key(
            op.f(f"fk_{table}_company_id_source_transaction_id_transactions"),
            table,
            "transactions",
            ["company_id", "source_transaction_id"],
            ["company_id", "id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            op.f(f"ck_{table}_source"),
            table,
            "(origin_journal_id IS NOT NULL AND origin_line_no IS NOT NULL) OR "
            "(source_invoice_id IS NOT NULL AND source_transaction_id IS NOT NULL "
            "AND recognized_date IS NOT NULL)",
        )
        op.drop_constraint(op.f(f"ck_{table}_amount"), table, type_="check")
        op.create_check_constraint(
            op.f(f"ck_{table}_amount"), table, "original_amount > 0 AND outstanding_amount >= 0"
        )
    for statement in DDL["obligation_adjustments"]:
        op.execute(statement)
    _protect_documents()


def _protect_documents() -> None:
    for table, lines in [
        ("sales_invoices", "sales_invoice_lines"),
        ("purchase_invoices", "purchase_invoice_lines"),
        ("document_notes", "document_note_lines"),
    ]:
        op.execute(f"""
            CREATE FUNCTION protect_{table}_approved() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE item_count integer; supply numeric; tax numeric;
            BEGIN
                IF TG_OP <> 'INSERT' AND OLD.status IN ('APPROVED','APPLIED') THEN
                    RAISE EXCEPTION 'confirmed document is immutable' USING ERRCODE='23514';
                END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                IF NEW.status <> 'DRAFT' THEN
                    SELECT count(*), sum(supply_amount), sum(tax_amount)
                    INTO item_count, supply, tax FROM {lines}
                    WHERE company_id=NEW.company_id AND invoice_id=NEW.id;
                    IF item_count < 1 OR supply <> NEW.supply_amount OR tax <> NEW.tax_amount THEN
                        RAISE EXCEPTION 'document total mismatch' USING ERRCODE='23514';
                    END IF;
                END IF;
                RETURN NEW;
            END $$;
            CREATE TRIGGER protect_{table}_approved BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION protect_{table}_approved();
        """)
    for table, parent in [
        ("sales_invoice_lines", "sales_invoices"),
        ("purchase_invoice_lines", "purchase_invoices"),
        ("document_note_lines", "document_notes"),
    ]:
        op.execute(f"""
            CREATE FUNCTION protect_{table}_approved() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE parent_status text;
            BEGIN
                IF TG_OP <> 'INSERT' THEN
                    SELECT status INTO parent_status FROM {parent}
                    WHERE company_id=OLD.company_id AND id=OLD.invoice_id FOR UPDATE;
                    IF parent_status <> 'DRAFT' THEN
                        RAISE EXCEPTION 'document lines are immutable' USING ERRCODE='23514';
                    END IF;
                END IF;
                IF TG_OP <> 'DELETE' THEN
                    SELECT status INTO parent_status FROM {parent}
                    WHERE company_id=NEW.company_id AND id=NEW.invoice_id FOR UPDATE;
                    IF parent_status <> 'DRAFT' THEN
                        RAISE EXCEPTION 'document lines are immutable' USING ERRCODE='23514';
                    END IF;
                    RETURN NEW;
                END IF;
                RETURN OLD;
            END $$;
            CREATE TRIGGER protect_{table}_approved BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION protect_{table}_approved();
        """)
    for table in ["business_document_events", "obligation_adjustments"]:
        op.execute(f"""
            CREATE FUNCTION protect_{table}_history() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'business history is append only' USING ERRCODE='23514';
            END $$;
            CREATE TRIGGER protect_{table}_history BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION protect_{table}_history();
        """)


def downgrade() -> None:
    connection = op.get_bind()
    if any(connection.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")) for table in DDL):
        raise RuntimeError(
            "업무문서 이력이 있는 DB는 백업 복구 또는 후속 수정 migration을 사용해 주세요."
        )
    for table in [
        "sales_invoices",
        "purchase_invoices",
        "document_notes",
        "sales_invoice_lines",
        "purchase_invoice_lines",
        "document_note_lines",
    ]:
        op.execute(f"DROP TRIGGER protect_{table}_approved ON {table}")
        op.execute(f"DROP FUNCTION protect_{table}_approved()")
    for table in ["business_document_events", "obligation_adjustments"]:
        op.execute(f"DROP TRIGGER protect_{table}_history ON {table}")
        op.execute(f"DROP FUNCTION protect_{table}_history()")
    op.drop_table("obligation_adjustments")
    for table, invoice in [("receivables", "sales_invoices"), ("payables", "purchase_invoices")]:
        op.drop_constraint(op.f(f"ck_{table}_source"), table, type_="check")
        op.drop_constraint(
            op.f(f"fk_{table}_company_id_source_invoice_id_{invoice}"), table, type_="foreignkey"
        )
        op.drop_constraint(
            op.f(f"fk_{table}_company_id_source_transaction_id_transactions"),
            table,
            type_="foreignkey",
        )
        for column in ["source_transaction_id", "source_invoice_id"]:
            op.drop_constraint(op.f(f"uq_{table}_company_id_{column}"), table, type_="unique")
            op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table)
            op.drop_column(table, column)
        op.drop_column(table, "recognized_date")
        op.alter_column(table, "origin_journal_id", nullable=False)
        op.alter_column(table, "origin_line_no", nullable=False)
        op.drop_constraint(op.f(f"ck_{table}_amount"), table, type_="check")
        op.create_check_constraint(
            op.f(f"ck_{table}_amount"),
            table,
            "original_amount > 0 AND outstanding_amount >= 0 "
            "AND outstanding_amount <= original_amount",
        )
    for table in reversed(list(DDL)):
        if table != "obligation_adjustments":
            op.drop_table(table)
