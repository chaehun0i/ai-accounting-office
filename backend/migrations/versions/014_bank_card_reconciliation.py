"""은행 카드 원천과 대사 관계를 순방향으로 보강합니다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014_bank_card_reconciliation"
down_revision: str | Sequence[str] | None = "013_business_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM reconciliation_match_lines) THEN "
        "RAISE EXCEPTION '기존 대사 행의 원천 FK 전환이 필요합니다'; END IF; END $$"
    )
    # 새 은행·카드 테이블과 기존 대사 FK를 순방향으로 보강합니다.
    op.create_table(
        "reconciliation_policies",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("allowed_days", sa.Integer(), nullable=False),
        sa.Column("amount_tolerance", sa.Numeric(19, 4), nullable=False),
        sa.Column("auto_threshold", sa.Integer(), nullable=False),
        sa.Column("review_threshold", sa.Integer(), nullable=False),
        sa.Column("materiality", sa.Numeric(19, 4), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "allowed_days BETWEEN 0 AND 90 AND version >= 1",
            name=op.f("ck_reconciliation_policies_days_version"),
        ),
        sa.CheckConstraint(
            "amount_tolerance >= 0 AND amount_tolerance < 1000000000000000 AND "
            "materiality >= 0 AND materiality < 1000000000000000",
            name=op.f("ck_reconciliation_policies_amounts"),
        ),
        sa.CheckConstraint(
            "review_threshold BETWEEN 0 AND 100 AND auto_threshold BETWEEN "
            "review_threshold AND 100",
            name=op.f("ck_reconciliation_policies_thresholds"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_reconciliation_policies_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_reconciliation_policies_updated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_policies")),
        sa.UniqueConstraint("company_id", name=op.f("uq_reconciliation_policies_company_id")),
    )
    op.create_table(
        "bank_accounts",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("institution_code", sa.String(length=30), nullable=False),
        sa.Column("alias", sa.String(length=80), nullable=False),
        sa.Column("control_account_id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("currency_code = 'KRW'", name=op.f("ck_bank_accounts_currency")),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name=op.f("ck_bank_accounts_status")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_bank_accounts_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "control_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            name=op.f("fk_bank_accounts_company_id_control_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_bank_accounts_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_accounts")),
        sa.UniqueConstraint("company_id", "alias", name=op.f("uq_bank_accounts_company_id_alias")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_bank_accounts_company_id_id")),
    )
    op.create_index(
        op.f("ix_bank_accounts_company_id"), "bank_accounts", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_bank_accounts_control_account_id"),
        "bank_accounts",
        ["control_account_id"],
        unique=False,
    )
    op.create_table(
        "card_accounts",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("institution_code", sa.String(length=30), nullable=False),
        sa.Column("alias", sa.String(length=80), nullable=False),
        sa.Column("control_account_id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("currency_code = 'KRW'", name=op.f("ck_card_accounts_currency")),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name=op.f("ck_card_accounts_status")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_card_accounts_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "control_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            name=op.f("fk_card_accounts_company_id_control_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_card_accounts_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card_accounts")),
        sa.UniqueConstraint("company_id", "alias", name=op.f("uq_card_accounts_company_id_alias")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_card_accounts_company_id_id")),
    )
    op.create_index(
        op.f("ix_card_accounts_company_id"), "card_accounts", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_card_accounts_control_account_id"),
        "card_accounts",
        ["control_account_id"],
        unique=False,
    )
    op.create_table(
        "bank_statements",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("statement_start", sa.Date(), nullable=False),
        sa.Column("statement_end", sa.Date(), nullable=False),
        sa.Column("opening_balance", sa.Numeric(19, 4), nullable=False),
        sa.Column("closing_balance", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source_import_id", sa.Uuid(), nullable=False),
        sa.Column("source_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("currency_code = 'KRW'", name=op.f("ck_bank_statements_currency")),
        sa.CheckConstraint(
            "status IN ('IMPORTED','RECONCILING','REVIEW_REQUIRED','RECONCILED','CLOSED')",
            name=op.f("ck_bank_statements_status"),
        ),
        sa.CheckConstraint(
            "abs(opening_balance) < 1000000000000000 AND abs(closing_balance) < 1000000000000000",
            name=op.f("ck_bank_statements_balances"),
        ),
        sa.CheckConstraint(
            "statement_start <= statement_end", name=op.f("ck_bank_statements_dates")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_bank_statements_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "bank_account_id"],
            ["bank_accounts.company_id", "bank_accounts.id"],
            name=op.f("fk_bank_statements_company_id_bank_account_id_bank_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_import_id", "source_receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            name=op.f(
                "fk_bank_statements_company_id_source_import_id_source_receipt_id_import_receipts"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_bank_statements_company_id_source_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_bank_statements_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_statements")),
        sa.UniqueConstraint(
            "company_id",
            "bank_account_id",
            "statement_start",
            "statement_end",
            name=op.f(
                "uq_bank_statements_company_id_bank_account_id_statement_start_statement_end"
            ),
        ),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_bank_statements_company_id_id")),
        sa.UniqueConstraint(
            "company_id",
            "source_import_id",
            name=op.f("uq_bank_statements_company_id_source_import_id"),
        ),
    )
    op.create_index(
        op.f("ix_bank_statements_bank_account_id"),
        "bank_statements",
        ["bank_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bank_statements_company_id"), "bank_statements", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_bank_statements_source_import_id"),
        "bank_statements",
        ["source_import_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bank_statements_source_receipt_id"),
        "bank_statements",
        ["source_receipt_id"],
        unique=False,
    )
    op.create_table(
        "card_transactions",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=3), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("counterparty_text", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("source_status", sa.String(length=16), nullable=False),
        sa.Column("source_import_id", sa.Uuid(), nullable=False),
        sa.Column("source_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("sheet_index", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "direction IN ('IN','OUT')", name=op.f("ck_card_transactions_direction")
        ),
        sa.CheckConstraint(
            "source_status IN ('AUTHORIZED','CAPTURED','CANCELLED','REFUNDED','REVERSED')",
            name=op.f("ck_card_transactions_source_status"),
        ),
        sa.CheckConstraint(
            "amount > 0 AND amount < 1000000000000000", name=op.f("ck_card_transactions_amount")
        ),
        sa.CheckConstraint(
            "version >= 1 AND sheet_index >= 0 AND row_number >= 2",
            name=op.f("ck_card_transactions_locator"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["card_accounts.company_id", "card_accounts.id"],
            name=op.f("fk_card_transactions_company_id_account_id_card_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_import_id", "source_receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            name=op.f(
                "fk_card_transactions_company_id_source_import_id_source_receipt_id_import_receipts"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_card_transactions_company_id_source_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_card_transactions_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card_transactions")),
        sa.UniqueConstraint(
            "company_id",
            "account_id",
            "source_system",
            "source_id",
            name=op.f("uq_card_transactions_company_id_account_id_source_system_source_id"),
        ),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_card_transactions_company_id_id")),
    )
    op.create_index(
        op.f("ix_card_transactions_account_id"), "card_transactions", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_card_transactions_company_id"), "card_transactions", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_card_transactions_occurred_at"), "card_transactions", ["occurred_at"], unique=False
    )
    op.create_index(
        op.f("ix_card_transactions_source_import_id"),
        "card_transactions",
        ["source_import_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_card_transactions_source_receipt_id"),
        "card_transactions",
        ["source_receipt_id"],
        unique=False,
    )
    op.create_table(
        "bank_transactions",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=3), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("counterparty_text", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("source_status", sa.String(length=16), nullable=False),
        sa.Column("source_import_id", sa.Uuid(), nullable=False),
        sa.Column("source_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("sheet_index", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Numeric(19, 4), nullable=True),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "direction IN ('IN','OUT')", name=op.f("ck_bank_transactions_direction")
        ),
        sa.CheckConstraint(
            "source_status IN ('AUTHORIZED','CAPTURED','CANCELLED','REFUNDED','REVERSED')",
            name=op.f("ck_bank_transactions_source_status"),
        ),
        sa.CheckConstraint(
            "amount > 0 AND amount < 1000000000000000", name=op.f("ck_bank_transactions_amount")
        ),
        sa.CheckConstraint(
            "version >= 1 AND sheet_index >= 0 AND row_number >= 2",
            name=op.f("ck_bank_transactions_locator"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["bank_accounts.company_id", "bank_accounts.id"],
            name=op.f("fk_bank_transactions_company_id_account_id_bank_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_import_id", "source_receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            name=op.f(
                "fk_bank_transactions_company_id_source_import_id_source_receipt_id_import_receipts"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_bank_transactions_company_id_source_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["bank_statements.company_id", "bank_statements.id"],
            name=op.f("fk_bank_transactions_company_id_statement_id_bank_statements"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_bank_transactions_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_transactions")),
        sa.UniqueConstraint(
            "company_id",
            "account_id",
            "source_system",
            "source_id",
            name=op.f("uq_bank_transactions_company_id_account_id_source_system_source_id"),
        ),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_bank_transactions_company_id_id")),
    )
    op.create_index(
        op.f("ix_bank_transactions_account_id"), "bank_transactions", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_bank_transactions_company_id"), "bank_transactions", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_bank_transactions_occurred_at"), "bank_transactions", ["occurred_at"], unique=False
    )
    op.create_index(
        op.f("ix_bank_transactions_source_import_id"),
        "bank_transactions",
        ["source_import_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bank_transactions_source_receipt_id"),
        "bank_transactions",
        ["source_receipt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bank_transactions_statement_id"),
        "bank_transactions",
        ["statement_id"],
        unique=False,
    )
    op.create_table(
        "reconciliation_events",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("command_code", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=True),
        sa.Column("reconciliation_id", sa.Uuid(), nullable=True),
        sa.Column("card_account_id", sa.Uuid(), nullable=True),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "num_nonnulls(statement_id,reconciliation_id,card_account_id) = 1",
            name=op.f("ck_reconciliation_events_result"),
        ),
        sa.CheckConstraint("result_version >= 1", name=op.f("ck_reconciliation_events_version")),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_reconciliation_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "card_account_id"],
            ["card_accounts.company_id", "card_accounts.id"],
            name=op.f("fk_reconciliation_events_company_id_card_account_id_card_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reconciliation_id"],
            ["reconciliation_matches.company_id", "reconciliation_matches.id"],
            name=op.f(
                "fk_reconciliation_events_company_id_reconciliation_id_reconciliation_matches"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["bank_statements.company_id", "bank_statements.id"],
            name=op.f("fk_reconciliation_events_company_id_statement_id_bank_statements"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_reconciliation_events_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_events")),
        sa.UniqueConstraint(
            "company_id",
            "actor_id",
            "command_code",
            "idempotency_key",
            name=op.f("uq_reconciliation_events_company_id_actor_id_command_code_idempotency_key"),
        ),
    )
    op.create_index(
        op.f("ix_reconciliation_events_card_account_id"),
        "reconciliation_events",
        ["card_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_events_company_id"),
        "reconciliation_events",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_events_reconciliation_id"),
        "reconciliation_events",
        ["reconciliation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_events_statement_id"),
        "reconciliation_events",
        ["statement_id"],
        unique=False,
    )
    op.create_table(
        "reconciliation_items",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "reason_code IN "
            "('TIMING_ITEM','MISSING_TRANSACTION','DUPLICATE_SOURCE','WRONG_ACCOUNT','MANUAL_ADJUSTMENT_CANDIDATE','UNKNOWN')",
            name=op.f("ck_reconciliation_items_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','RESOLVED')", name=op.f("ck_reconciliation_items_status")
        ),
        sa.CheckConstraint(
            "abs(amount) < 1000000000000000", name=op.f("ck_reconciliation_items_amount")
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["bank_statements.company_id", "bank_statements.id"],
            name=op.f("fk_reconciliation_items_company_id_statement_id_bank_statements"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_reconciliation_items_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_reconciliation_items_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_items")),
    )
    op.create_index(
        op.f("ix_reconciliation_items_company_id"),
        "reconciliation_items",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_items_statement_id"),
        "reconciliation_items",
        ["statement_id"],
        unique=False,
    )
    op.add_column(
        "chart_of_accounts", sa.Column("control_account_type", sa.String(length=24), nullable=True)
    )
    op.add_column(
        "reconciliation_match_lines",
        sa.Column("source_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "reconciliation_match_lines",
        sa.Column("target_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "reconciliation_match_lines", sa.Column("bank_transaction_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "reconciliation_match_lines", sa.Column("card_transaction_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "reconciliation_match_lines", sa.Column("collection_id", sa.Uuid(), nullable=True)
    )
    op.add_column("reconciliation_match_lines", sa.Column("payment_id", sa.Uuid(), nullable=True))
    op.add_column(
        "reconciliation_match_lines", sa.Column("transaction_id", sa.Uuid(), nullable=True)
    )
    op.create_index(
        op.f("ix_reconciliation_match_lines_bank_transaction_id"),
        "reconciliation_match_lines",
        ["bank_transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_match_lines_card_transaction_id"),
        "reconciliation_match_lines",
        ["card_transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_match_lines_collection_id"),
        "reconciliation_match_lines",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_match_lines_payment_id"),
        "reconciliation_match_lines",
        ["payment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_match_lines_transaction_id"),
        "reconciliation_match_lines",
        ["transaction_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_reconciliation_match_lines_company_id_payment_id_payments"),
        "reconciliation_match_lines",
        "payments",
        ["company_id", "payment_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_reconciliation_match_lines_company_id_card_transaction_id_card_transactions"),
        "reconciliation_match_lines",
        "card_transactions",
        ["company_id", "card_transaction_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_reconciliation_match_lines_company_id_collection_id_collections"),
        "reconciliation_match_lines",
        "collections",
        ["company_id", "collection_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_reconciliation_match_lines_company_id_bank_transaction_id_bank_transactions"),
        "reconciliation_match_lines",
        "bank_transactions",
        ["company_id", "bank_transaction_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_reconciliation_match_lines_company_id_transaction_id_transactions"),
        "reconciliation_match_lines",
        "transactions",
        ["company_id", "transaction_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "reconciliation_matches",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("reconciliation_matches", sa.Column("confirmed_by", sa.Uuid(), nullable=True))
    op.add_column(
        "reconciliation_matches",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("reconciliation_matches", sa.Column("unmatched_by", sa.Uuid(), nullable=True))
    op.add_column(
        "reconciliation_matches",
        sa.Column("unmatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reconciliation_matches", sa.Column("unmatch_reason", sa.String(length=500), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_reconciliation_matches_unmatched_by_users"),
        "reconciliation_matches",
        "users",
        ["unmatched_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_reconciliation_matches_confirmed_by_users"),
        "reconciliation_matches",
        "users",
        ["confirmed_by"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        op.f("ck_reconciliation_matches_status"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_status"),
        "reconciliation_matches",
        "status IN ('DRAFT','CONFIRMED','UNMATCHED')",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_matches_amount"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_amount"),
        "reconciliation_matches",
        "matched_amount > 0 AND matched_amount < 1000000000000000",
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_version"), "reconciliation_matches", "version >= 1"
    )
    op.create_check_constraint(
        op.f("ck_chart_of_accounts_control_role"),
        "chart_of_accounts",
        "control_account_type IS NULL OR (control_account_type = 'BANK_CASH' AND "
        "account_type = 'ASSET') OR (control_account_type = 'CARD_PAYABLE' AND "
        "account_type = 'LIABILITY')",
    )
    op.drop_constraint(op.f("ck_imports_target"), "imports", type_="check")
    op.create_check_constraint(
        op.f("ck_imports_target"),
        "imports",
        "target_context IN "
        "('TRANSACTION_CANONICAL','ONBOARDING_DRAFT','DOMAIN_MASTER','BANK_SOURCE','CARD_SOURCE')",
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_match_lines_typed_references"),
        "reconciliation_match_lines",
        "num_nonnulls(bank_transaction_id,card_transaction_id) = 1 AND "
        "num_nonnulls(collection_id,payment_id,transaction_id) = 1",
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_match_lines_source_identity"),
        "reconciliation_match_lines",
        "(source_type = 'BANK' AND source_id = bank_transaction_id AND "
        "bank_transaction_id IS NOT NULL) OR (source_type = 'CARD' AND source_id = "
        "card_transaction_id AND card_transaction_id IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_match_lines_target_identity"),
        "reconciliation_match_lines",
        "(target_type = 'COLLECTION' AND target_id = collection_id AND "
        "collection_id IS NOT NULL) OR (target_type = 'PAYMENT' AND target_id = "
        "payment_id AND payment_id IS NOT NULL) OR (target_type = 'TRANSACTION' AND "
        "target_id = transaction_id AND transaction_id IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_match_lines_versions"),
        "reconciliation_match_lines",
        "source_version >= 1 AND target_version >= 1",
    )

    # 원천 사실과 대사 이력은 새 이벤트를 통해서만 정정합니다.
    for table in ("bank_transactions", "card_transactions", "bank_statements"):
        op.execute(f"""
            CREATE FUNCTION protect_{table}_facts() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'financial source history is immutable';
                END IF;
                IF (to_jsonb(NEW) - 'version' - 'status') IS DISTINCT FROM
                   (to_jsonb(OLD) - 'version' - 'status') OR NEW.version <> OLD.version + 1 THEN
                    RAISE EXCEPTION 'financial source facts are immutable';
                END IF;
                RETURN NEW;
            END $$;
            CREATE TRIGGER protect_{table}_facts BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION protect_{table}_facts();
        """)
    for table in ("reconciliation_events", "reconciliation_match_lines"):
        op.execute(f"""
            CREATE FUNCTION protect_{table}_history() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'reconciliation history is append-only'; END $$;
            CREATE TRIGGER protect_{table}_history BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION protect_{table}_history();
        """)


def downgrade() -> None:
    # 문서·금융 원천을 버리는 downgrade는 금지합니다.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM bank_transactions) OR EXISTS (SELECT "
        "1 FROM card_transactions) OR EXISTS (SELECT 1 FROM bank_statements) OR "
        "EXISTS (SELECT 1 FROM reconciliation_events) THEN RAISE EXCEPTION '금융 원천이 "
        "있어 downgrade할 수 없습니다'; END IF; END $$"
    )
    for table in ("bank_transactions", "card_transactions", "bank_statements"):
        op.execute(f"DROP TRIGGER protect_{table}_facts ON {table}")
        op.execute(f"DROP FUNCTION protect_{table}_facts()")
    for table in ("reconciliation_events", "reconciliation_match_lines"):
        op.execute(f"DROP TRIGGER protect_{table}_history ON {table}")
        op.execute(f"DROP FUNCTION protect_{table}_history()")
    op.drop_constraint(
        op.f("ck_chart_of_accounts_control_role"), "chart_of_accounts", type_="check"
    )
    op.drop_constraint(
        op.f("ck_reconciliation_matches_version"), "reconciliation_matches", type_="check"
    )
    op.drop_constraint(
        op.f("ck_reconciliation_matches_status"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_status"),
        "reconciliation_matches",
        "status IN ('DRAFT','CONFIRMED')",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_matches_amount"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_amount"), "reconciliation_matches", "matched_amount > 0"
    )
    op.drop_constraint(op.f("ck_imports_target"), "imports", type_="check")
    op.create_check_constraint(
        op.f("ck_imports_target"),
        "imports",
        "target_context IN ('TRANSACTION_CANONICAL','ONBOARDING_DRAFT','DOMAIN_MASTER')",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_match_lines_typed_references"),
        "reconciliation_match_lines",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_match_lines_source_identity"),
        "reconciliation_match_lines",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_match_lines_target_identity"),
        "reconciliation_match_lines",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_match_lines_versions"), "reconciliation_match_lines", type_="check"
    )

    # 새 은행·카드 테이블과 기존 대사 FK를 순방향으로 보강합니다.
    op.drop_constraint(
        op.f("fk_reconciliation_matches_confirmed_by_users"),
        "reconciliation_matches",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_reconciliation_matches_unmatched_by_users"),
        "reconciliation_matches",
        type_="foreignkey",
    )
    op.drop_column("reconciliation_matches", "unmatch_reason")
    op.drop_column("reconciliation_matches", "unmatched_at")
    op.drop_column("reconciliation_matches", "unmatched_by")
    op.drop_column("reconciliation_matches", "confirmed_at")
    op.drop_column("reconciliation_matches", "confirmed_by")
    op.drop_column("reconciliation_matches", "version")
    op.drop_constraint(
        op.f("fk_reconciliation_match_lines_company_id_transaction_id_transactions"),
        "reconciliation_match_lines",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_reconciliation_match_lines_company_id_bank_transaction_id_bank_transactions"),
        "reconciliation_match_lines",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_reconciliation_match_lines_company_id_collection_id_collections"),
        "reconciliation_match_lines",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_reconciliation_match_lines_company_id_card_transaction_id_card_transactions"),
        "reconciliation_match_lines",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_reconciliation_match_lines_company_id_payment_id_payments"),
        "reconciliation_match_lines",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_reconciliation_match_lines_transaction_id"),
        table_name="reconciliation_match_lines",
    )
    op.drop_index(
        op.f("ix_reconciliation_match_lines_payment_id"), table_name="reconciliation_match_lines"
    )
    op.drop_index(
        op.f("ix_reconciliation_match_lines_collection_id"), table_name="reconciliation_match_lines"
    )
    op.drop_index(
        op.f("ix_reconciliation_match_lines_card_transaction_id"),
        table_name="reconciliation_match_lines",
    )
    op.drop_index(
        op.f("ix_reconciliation_match_lines_bank_transaction_id"),
        table_name="reconciliation_match_lines",
    )
    op.drop_column("reconciliation_match_lines", "transaction_id")
    op.drop_column("reconciliation_match_lines", "payment_id")
    op.drop_column("reconciliation_match_lines", "collection_id")
    op.drop_column("reconciliation_match_lines", "card_transaction_id")
    op.drop_column("reconciliation_match_lines", "bank_transaction_id")
    op.drop_column("reconciliation_match_lines", "target_version")
    op.drop_column("reconciliation_match_lines", "source_version")
    op.drop_column("chart_of_accounts", "control_account_type")
    op.drop_index(op.f("ix_reconciliation_items_statement_id"), table_name="reconciliation_items")
    op.drop_index(op.f("ix_reconciliation_items_company_id"), table_name="reconciliation_items")
    op.drop_table("reconciliation_items")
    op.drop_index(op.f("ix_reconciliation_events_statement_id"), table_name="reconciliation_events")
    op.drop_index(
        op.f("ix_reconciliation_events_reconciliation_id"), table_name="reconciliation_events"
    )
    op.drop_index(op.f("ix_reconciliation_events_company_id"), table_name="reconciliation_events")
    op.drop_index(
        op.f("ix_reconciliation_events_card_account_id"), table_name="reconciliation_events"
    )
    op.drop_table("reconciliation_events")
    op.drop_index(op.f("ix_bank_transactions_statement_id"), table_name="bank_transactions")
    op.drop_index(op.f("ix_bank_transactions_source_receipt_id"), table_name="bank_transactions")
    op.drop_index(op.f("ix_bank_transactions_source_import_id"), table_name="bank_transactions")
    op.drop_index(op.f("ix_bank_transactions_occurred_at"), table_name="bank_transactions")
    op.drop_index(op.f("ix_bank_transactions_company_id"), table_name="bank_transactions")
    op.drop_index(op.f("ix_bank_transactions_account_id"), table_name="bank_transactions")
    op.drop_table("bank_transactions")
    op.drop_index(op.f("ix_card_transactions_source_receipt_id"), table_name="card_transactions")
    op.drop_index(op.f("ix_card_transactions_source_import_id"), table_name="card_transactions")
    op.drop_index(op.f("ix_card_transactions_occurred_at"), table_name="card_transactions")
    op.drop_index(op.f("ix_card_transactions_company_id"), table_name="card_transactions")
    op.drop_index(op.f("ix_card_transactions_account_id"), table_name="card_transactions")
    op.drop_table("card_transactions")
    op.drop_index(op.f("ix_bank_statements_source_receipt_id"), table_name="bank_statements")
    op.drop_index(op.f("ix_bank_statements_source_import_id"), table_name="bank_statements")
    op.drop_index(op.f("ix_bank_statements_company_id"), table_name="bank_statements")
    op.drop_index(op.f("ix_bank_statements_bank_account_id"), table_name="bank_statements")
    op.drop_table("bank_statements")
    op.drop_index(op.f("ix_card_accounts_control_account_id"), table_name="card_accounts")
    op.drop_index(op.f("ix_card_accounts_company_id"), table_name="card_accounts")
    op.drop_table("card_accounts")
    op.drop_index(op.f("ix_bank_accounts_control_account_id"), table_name="bank_accounts")
    op.drop_index(op.f("ix_bank_accounts_company_id"), table_name="bank_accounts")
    op.drop_table("bank_accounts")
    op.drop_table("reconciliation_policies")
