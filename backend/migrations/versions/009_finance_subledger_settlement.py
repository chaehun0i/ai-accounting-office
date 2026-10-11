"""재무 보조부 정산 관계형 구조

리비전: 009_finance_subledger
이전 리비전: 008_governance
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_finance_subledger"
down_revision: str | Sequence[str] | None = "008_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 관계형 재무 보조부와 회사 범위 제약을 생성합니다.
    op.create_table(
        "reconciliation_matches",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("match_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "matched_amount",
            sa.Numeric(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT','CONFIRMED')", name=op.f("ck_reconciliation_matches_status")
        ),
        sa.CheckConstraint("matched_amount > 0", name=op.f("ck_reconciliation_matches_amount")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_reconciliation_matches_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_reconciliation_matches_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_matches")),
        sa.UniqueConstraint(
            "company_id", "id", name=op.f("uq_reconciliation_matches_company_id_id")
        ),
    )
    op.create_index(
        op.f("ix_reconciliation_matches_company_id"),
        "reconciliation_matches",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_matches_created_by"),
        "reconciliation_matches",
        ["created_by"],
        unique=False,
    )
    op.create_table(
        "reconciliation_match_lines",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("reconciliation_match_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_reconciliation_match_lines_amount")),
        sa.ForeignKeyConstraint(
            ["company_id", "reconciliation_match_id"],
            ["reconciliation_matches.company_id", "reconciliation_matches.id"],
            name=op.f(
                "fk_reconciliation_match_lines_company_id_reconciliation_match_id_reconciliation_matches"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_reconciliation_match_lines_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_match_lines")),
    )
    op.create_index(
        op.f("ix_reconciliation_match_lines_company_id"),
        "reconciliation_match_lines",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_match_lines_reconciliation_match_id"),
        "reconciliation_match_lines",
        ["reconciliation_match_id"],
        unique=False,
    )
    op.create_table(
        "collections",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("received_date", sa.Date(), nullable=False),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("reference_no", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
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
            "(status='DRAFT' AND confirmed_at IS NULL) OR (status<>'DRAFT' AND confirmed_at IS NOT NULL)",
            name=op.f("ck_collections_confirmed"),
        ),
        sa.CheckConstraint("currency_code='KRW'", name=op.f("ck_collections_currency")),
        sa.CheckConstraint(
            "method IN ('BANK_TRANSFER','CASH','OTHER')", name=op.f("ck_collections_method")
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','UNAPPLIED')", name=op.f("ck_collections_status")
        ),
        sa.CheckConstraint("total_amount > 0", name=op.f("ck_collections_amount")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_collections_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_collections_company_id_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_collections_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_collections_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collections")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_collections_company_id_id")),
        sa.UniqueConstraint(
            "company_id",
            "journal_entry_id",
            name=op.f("uq_collections_company_id_journal_entry_id"),
        ),
    )
    op.create_index(op.f("ix_collections_company_id"), "collections", ["company_id"], unique=False)
    op.create_index(op.f("ix_collections_created_by"), "collections", ["created_by"], unique=False)
    op.create_index(
        op.f("ix_collections_journal_entry_id"), "collections", ["journal_entry_id"], unique=False
    )
    op.create_index(
        op.f("ix_collections_received_date"), "collections", ["received_date"], unique=False
    )
    op.create_table(
        "payments",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("reference_no", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
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
            "(status='DRAFT' AND confirmed_at IS NULL) OR (status<>'DRAFT' AND confirmed_at IS NOT NULL)",
            name=op.f("ck_payments_confirmed"),
        ),
        sa.CheckConstraint("currency_code='KRW'", name=op.f("ck_payments_currency")),
        sa.CheckConstraint(
            "method IN ('BANK_TRANSFER','CASH','OTHER')", name=op.f("ck_payments_method")
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','UNAPPLIED')", name=op.f("ck_payments_status")
        ),
        sa.CheckConstraint("total_amount > 0", name=op.f("ck_payments_amount")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_payments_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_payments_company_id_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_payments_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_payments_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_payments_company_id_id")),
        sa.UniqueConstraint(
            "company_id", "journal_entry_id", name=op.f("uq_payments_company_id_journal_entry_id")
        ),
    )
    op.create_index(op.f("ix_payments_company_id"), "payments", ["company_id"], unique=False)
    op.create_index(op.f("ix_payments_created_by"), "payments", ["created_by"], unique=False)
    op.create_index(
        op.f("ix_payments_journal_entry_id"), "payments", ["journal_entry_id"], unique=False
    )
    op.create_index(op.f("ix_payments_payment_date"), "payments", ["payment_date"], unique=False)
    op.create_table(
        "finance_command_receipts",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("command_code", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(collection_id IS NULL) <> (payment_id IS NULL)",
            name=op.f("ck_finance_command_receipts_resource"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_finance_command_receipts_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "collection_id"],
            ["collections.company_id", "collections.id"],
            name=op.f("fk_finance_command_receipts_company_id_collection_id_collections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "payment_id"],
            ["payments.company_id", "payments.id"],
            name=op.f("fk_finance_command_receipts_company_id_payment_id_payments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_finance_command_receipts_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finance_command_receipts")),
        sa.UniqueConstraint(
            "company_id",
            "actor_id",
            "command_code",
            "idempotency_key",
            name=op.f(
                "uq_finance_command_receipts_company_id_actor_id_command_code_idempotency_key"
            ),
        ),
    )
    op.create_index(
        op.f("ix_finance_command_receipts_actor_id"),
        "finance_command_receipts",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finance_command_receipts_collection_id"),
        "finance_command_receipts",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finance_command_receipts_company_id"),
        "finance_command_receipts",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finance_command_receipts_payment_id"),
        "finance_command_receipts",
        ["payment_id"],
        unique=False,
    )
    op.create_table(
        "payables",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_id", sa.Uuid(), nullable=False),
        sa.Column("origin_journal_id", sa.Uuid(), nullable=False),
        sa.Column("origin_line_no", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "original_amount",
            sa.Numeric(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column(
            "outstanding_amount",
            sa.Numeric(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
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
        sa.CheckConstraint("currency_code='KRW'", name=op.f("ck_payables_currency")),
        sa.CheckConstraint(
            "status IN ('OPEN','PARTIAL','SETTLED','CANCELLED','WRITEOFF')",
            name=op.f("ck_payables_status"),
        ),
        sa.CheckConstraint(
            "original_amount > 0 AND outstanding_amount >= 0 AND outstanding_amount <= original_amount",
            name=op.f("ck_payables_amount"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_payables_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            name=op.f("fk_payables_company_id_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "counterparty_id"],
            ["counterparties.company_id", "counterparties.id"],
            name=op.f("fk_payables_company_id_counterparty_id_counterparties"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "origin_journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_payables_company_id_origin_journal_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_payables_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origin_journal_id", "origin_line_no"],
            ["journal_lines.journal_entry_id", "journal_lines.line_no"],
            name=op.f("fk_payables_origin_journal_id_origin_line_no_journal_lines"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payables")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_payables_company_id_id")),
        sa.UniqueConstraint(
            "company_id",
            "origin_journal_id",
            "origin_line_no",
            name=op.f("uq_payables_company_id_origin_journal_id_origin_line_no"),
        ),
    )
    op.create_index(op.f("ix_payables_account_id"), "payables", ["account_id"], unique=False)
    op.create_index(op.f("ix_payables_company_id"), "payables", ["company_id"], unique=False)
    op.create_index(
        op.f("ix_payables_counterparty_id"), "payables", ["counterparty_id"], unique=False
    )
    op.create_index(op.f("ix_payables_due_date"), "payables", ["due_date"], unique=False)
    op.create_index(
        op.f("ix_payables_origin_journal_id"), "payables", ["origin_journal_id"], unique=False
    )
    op.create_table(
        "receivables",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_id", sa.Uuid(), nullable=False),
        sa.Column("origin_journal_id", sa.Uuid(), nullable=False),
        sa.Column("origin_line_no", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "original_amount",
            sa.Numeric(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column(
            "outstanding_amount",
            sa.Numeric(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
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
        sa.CheckConstraint("currency_code='KRW'", name=op.f("ck_receivables_currency")),
        sa.CheckConstraint(
            "status IN ('OPEN','PARTIAL','SETTLED','WRITEOFF')", name=op.f("ck_receivables_status")
        ),
        sa.CheckConstraint(
            "original_amount > 0 AND outstanding_amount >= 0 AND outstanding_amount <= original_amount",
            name=op.f("ck_receivables_amount"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_receivables_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            name=op.f("fk_receivables_company_id_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "counterparty_id"],
            ["counterparties.company_id", "counterparties.id"],
            name=op.f("fk_receivables_company_id_counterparty_id_counterparties"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "origin_journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_receivables_company_id_origin_journal_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_receivables_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origin_journal_id", "origin_line_no"],
            ["journal_lines.journal_entry_id", "journal_lines.line_no"],
            name=op.f("fk_receivables_origin_journal_id_origin_line_no_journal_lines"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receivables")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_receivables_company_id_id")),
        sa.UniqueConstraint(
            "company_id",
            "origin_journal_id",
            "origin_line_no",
            name=op.f("uq_receivables_company_id_origin_journal_id_origin_line_no"),
        ),
    )
    op.create_index(op.f("ix_receivables_account_id"), "receivables", ["account_id"], unique=False)
    op.create_index(op.f("ix_receivables_company_id"), "receivables", ["company_id"], unique=False)
    op.create_index(
        op.f("ix_receivables_counterparty_id"), "receivables", ["counterparty_id"], unique=False
    )
    op.create_index(op.f("ix_receivables_due_date"), "receivables", ["due_date"], unique=False)
    op.create_index(
        op.f("ix_receivables_origin_journal_id"), "receivables", ["origin_journal_id"], unique=False
    )
    op.create_table(
        "collection_allocations",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("receivable_id", sa.Uuid(), nullable=False),
        sa.Column(
            "allocated_amount",
            sa.Numeric(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("allocated_amount > 0", name=op.f("ck_collection_allocations_amount")),
        sa.CheckConstraint("expected_version >= 1", name=op.f("ck_collection_allocations_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "collection_id"],
            ["collections.company_id", "collections.id"],
            name=op.f("fk_collection_allocations_company_id_collection_id_collections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "receivable_id"],
            ["receivables.company_id", "receivables.id"],
            name=op.f("fk_collection_allocations_company_id_receivable_id_receivables"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_collection_allocations_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_allocations")),
        sa.UniqueConstraint(
            "collection_id",
            "receivable_id",
            name=op.f("uq_collection_allocations_collection_id_receivable_id"),
        ),
    )
    op.create_index(
        op.f("ix_collection_allocations_collection_id"),
        "collection_allocations",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_allocations_company_id"),
        "collection_allocations",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_allocations_receivable_id"),
        "collection_allocations",
        ["receivable_id"],
        unique=False,
    )
    op.create_table(
        "payment_allocations",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("payable_id", sa.Uuid(), nullable=False),
        sa.Column(
            "allocated_amount",
            sa.Numeric(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("allocated_amount > 0", name=op.f("ck_payment_allocations_amount")),
        sa.CheckConstraint("expected_version >= 1", name=op.f("ck_payment_allocations_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "payable_id"],
            ["payables.company_id", "payables.id"],
            name=op.f("fk_payment_allocations_company_id_payable_id_payables"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "payment_id"],
            ["payments.company_id", "payments.id"],
            name=op.f("fk_payment_allocations_company_id_payment_id_payments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_payment_allocations_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_allocations")),
        sa.UniqueConstraint(
            "payment_id", "payable_id", name=op.f("uq_payment_allocations_payment_id_payable_id")
        ),
    )
    op.create_index(
        op.f("ix_payment_allocations_company_id"),
        "payment_allocations",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_allocations_payable_id"),
        "payment_allocations",
        ["payable_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_allocations_payment_id"),
        "payment_allocations",
        ["payment_id"],
        unique=False,
    )
    # 재무 보조부 스키마 변경 끝.


def downgrade() -> None:
    # 관계형 재무 보조부와 회사 범위 제약을 생성합니다.
    op.drop_index(op.f("ix_payment_allocations_payment_id"), table_name="payment_allocations")
    op.drop_index(op.f("ix_payment_allocations_payable_id"), table_name="payment_allocations")
    op.drop_index(op.f("ix_payment_allocations_company_id"), table_name="payment_allocations")
    op.drop_table("payment_allocations")
    op.drop_index(
        op.f("ix_collection_allocations_receivable_id"), table_name="collection_allocations"
    )
    op.drop_index(op.f("ix_collection_allocations_company_id"), table_name="collection_allocations")
    op.drop_index(
        op.f("ix_collection_allocations_collection_id"), table_name="collection_allocations"
    )
    op.drop_table("collection_allocations")
    op.drop_index(op.f("ix_receivables_origin_journal_id"), table_name="receivables")
    op.drop_index(op.f("ix_receivables_due_date"), table_name="receivables")
    op.drop_index(op.f("ix_receivables_counterparty_id"), table_name="receivables")
    op.drop_index(op.f("ix_receivables_company_id"), table_name="receivables")
    op.drop_index(op.f("ix_receivables_account_id"), table_name="receivables")
    op.drop_table("receivables")
    op.drop_index(op.f("ix_payables_origin_journal_id"), table_name="payables")
    op.drop_index(op.f("ix_payables_due_date"), table_name="payables")
    op.drop_index(op.f("ix_payables_counterparty_id"), table_name="payables")
    op.drop_index(op.f("ix_payables_company_id"), table_name="payables")
    op.drop_index(op.f("ix_payables_account_id"), table_name="payables")
    op.drop_table("payables")
    op.drop_index(
        op.f("ix_finance_command_receipts_payment_id"), table_name="finance_command_receipts"
    )
    op.drop_index(
        op.f("ix_finance_command_receipts_company_id"), table_name="finance_command_receipts"
    )
    op.drop_index(
        op.f("ix_finance_command_receipts_collection_id"), table_name="finance_command_receipts"
    )
    op.drop_index(
        op.f("ix_finance_command_receipts_actor_id"), table_name="finance_command_receipts"
    )
    op.drop_table("finance_command_receipts")
    op.drop_index(op.f("ix_payments_payment_date"), table_name="payments")
    op.drop_index(op.f("ix_payments_journal_entry_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_created_by"), table_name="payments")
    op.drop_index(op.f("ix_payments_company_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_collections_received_date"), table_name="collections")
    op.drop_index(op.f("ix_collections_journal_entry_id"), table_name="collections")
    op.drop_index(op.f("ix_collections_created_by"), table_name="collections")
    op.drop_index(op.f("ix_collections_company_id"), table_name="collections")
    op.drop_table("collections")
    op.drop_index(
        op.f("ix_reconciliation_match_lines_reconciliation_match_id"),
        table_name="reconciliation_match_lines",
    )
    op.drop_index(
        op.f("ix_reconciliation_match_lines_company_id"), table_name="reconciliation_match_lines"
    )
    op.drop_table("reconciliation_match_lines")
    op.drop_index(op.f("ix_reconciliation_matches_created_by"), table_name="reconciliation_matches")
    op.drop_index(op.f("ix_reconciliation_matches_company_id"), table_name="reconciliation_matches")
    op.drop_table("reconciliation_matches")
    # 재무 보조부 스키마 변경 끝.
