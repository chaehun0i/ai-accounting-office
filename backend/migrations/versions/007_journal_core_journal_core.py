"""복식부기 전표와 분개 기반

리비전: 007_journal_core
이전 리비전: 006_transactions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_journal_core"
down_revision: str | Sequence[str] | None = "006_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_accounting_periods_company_id_id"), "accounting_periods", ["company_id", "id"]
    )
    # 회사 경계와 복식부기 제약을 명시적으로 생성합니다.
    op.create_table(
        "journal_entries",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
        sa.Column("source_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("proposal_origin", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("journal_no", sa.String(length=80), nullable=True),
        sa.Column("reversal_of_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("posted_by", sa.Uuid(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
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
            "(status='POSTED' AND journal_no IS NOT NULL AND posted_at IS NOT NULL AND "
            "posted_by IS NOT NULL AND approval_id IS NOT NULL) "
            "OR (status<>'POSTED' AND journal_no IS NULL AND posted_at IS NULL)",
            name=op.f("ck_journal_entries_posted"),
        ),
        sa.CheckConstraint(
            "source_type IN ('MANUAL','TRANSACTION','OPENING','REVERSAL')",
            name=op.f("ck_journal_entries_source"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','PROPOSED','REVIEW_REQUIRED','APPROVED','REJECTED','POSTED')",
            name=op.f("ck_journal_entries_status"),
        ),
        sa.CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id <> id",
            name=op.f("ck_journal_entries_reversal"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_journal_entries_version")),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name=op.f("fk_journal_entries_approved_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "accounting_period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            name=op.f("fk_journal_entries_company_id_accounting_period_id_accounting_periods"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reversal_of_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_journal_entries_company_id_reversal_of_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_transaction_id"],
            ["transactions.company_id", "transactions.id"],
            name=op.f("fk_journal_entries_company_id_source_transaction_id_transactions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_journal_entries_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_journal_entries_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_by"],
            ["users.id"],
            name=op.f("fk_journal_entries_posted_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entries")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_journal_entries_company_id_id")),
        sa.UniqueConstraint(
            "company_id", "journal_no", name=op.f("uq_journal_entries_company_id_journal_no")
        ),
        sa.UniqueConstraint(
            "company_id",
            "reversal_of_id",
            name=op.f("uq_journal_entries_company_id_reversal_of_id"),
        ),
    )
    op.create_index(
        op.f("ix_journal_entries_accounting_period_id"),
        "journal_entries",
        ["accounting_period_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_journal_entries_approval_id"), "journal_entries", ["approval_id"], unique=False
    )
    op.create_index(
        op.f("ix_journal_entries_approved_by"), "journal_entries", ["approved_by"], unique=False
    )
    op.create_index(
        op.f("ix_journal_entries_company_id"), "journal_entries", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_journal_entries_created_by"), "journal_entries", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_journal_entries_entry_date"), "journal_entries", ["entry_date"], unique=False
    )
    op.create_index(
        op.f("ix_journal_entries_posted_by"), "journal_entries", ["posted_by"], unique=False
    )
    op.create_index(
        op.f("ix_journal_entries_reversal_of_id"),
        "journal_entries",
        ["reversal_of_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_journal_entries_source_transaction_id"),
        "journal_entries",
        ["source_transaction_id"],
        unique=False,
    )
    op.create_index(op.f("ix_journal_entries_status"), "journal_entries", ["status"], unique=False)
    op.create_table(
        "journal_evidences",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            name=op.f("fk_journal_evidences_company_id_evidence_id_evidences"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_journal_evidences_company_id_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_journal_evidences_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_evidences")),
        sa.UniqueConstraint(
            "journal_entry_id",
            "evidence_id",
            name=op.f("uq_journal_evidences_journal_entry_id_evidence_id"),
        ),
    )
    op.create_index(
        op.f("ix_journal_evidences_company_id"), "journal_evidences", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_journal_evidences_evidence_id"), "journal_evidences", ["evidence_id"], unique=False
    )
    op.create_index(
        op.f("ix_journal_evidences_journal_entry_id"),
        "journal_evidences",
        ["journal_entry_id"],
        unique=False,
    )
    op.create_table(
        "journal_lines",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_id", sa.Uuid(), nullable=True),
        sa.Column("debit_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("credit_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("memo", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0)",
            name=op.f("ck_journal_lines_amount_side"),
        ),
        sa.CheckConstraint("line_no > 0", name=op.f("ck_journal_lines_line_no")),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            name=op.f("fk_journal_lines_company_id_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "counterparty_id"],
            ["counterparties.company_id", "counterparties.id"],
            name=op.f("fk_journal_lines_company_id_counterparty_id_counterparties"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_journal_lines_company_id_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_journal_lines_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_lines")),
        sa.UniqueConstraint(
            "journal_entry_id", "line_no", name=op.f("uq_journal_lines_journal_entry_id_line_no")
        ),
    )
    op.create_index(
        op.f("ix_journal_lines_account_id"), "journal_lines", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_journal_lines_company_id"), "journal_lines", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_journal_lines_counterparty_id"), "journal_lines", ["counterparty_id"], unique=False
    )
    op.create_index(
        op.f("ix_journal_lines_journal_entry_id"),
        "journal_lines",
        ["journal_entry_id"],
        unique=False,
    )
    op.create_table(
        "journal_proposals",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reason_summary", sa.Text(), nullable=False),
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
        sa.CheckConstraint("version >= 1", name=op.f("ck_journal_proposals_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_entry_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_journal_proposals_company_id_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "transaction_id"],
            ["transactions.company_id", "transactions.id"],
            name=op.f("fk_journal_proposals_company_id_transaction_id_transactions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_journal_proposals_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_proposals")),
    )
    op.create_index(
        op.f("ix_journal_proposals_company_id"), "journal_proposals", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_journal_proposals_journal_entry_id"),
        "journal_proposals",
        ["journal_entry_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_journal_proposals_transaction_id"),
        "journal_proposals",
        ["transaction_id"],
        unique=False,
    )

    # 기초잔액 입력 스냅샷은 전표와 관계형으로 연결합니다.
    op.create_table(
        "opening_balance_imports",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("onboarding_session_id", sa.Uuid(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("journal_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "onboarding_session_id",
            name="uq_opening_balance_imports_company_id_onboarding_session_id",
        ),
        sa.CheckConstraint("source_version>=1", name=op.f("ck_opening_balance_imports_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_opening_balance_imports_company_id_journal_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "onboarding_session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            name=op.f(
                "fk_opening_balance_imports_company_id_onboarding_session_id_onboarding_sessions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_opening_balance_imports_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_opening_balance_imports_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opening_balance_imports")),
        sa.UniqueConstraint(
            "company_id", "id", name=op.f("uq_opening_balance_imports_company_id_id")
        ),
        sa.UniqueConstraint(
            "company_id",
            "onboarding_session_id",
            "source_version",
            name=op.f("uq_opening_balance_imports_company_id_onboarding_session_id_source_version"),
        ),
    )
    op.create_index(
        op.f("ix_opening_balance_imports_company_id"),
        "opening_balance_imports",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opening_balance_imports_created_by"),
        "opening_balance_imports",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opening_balance_imports_journal_id"),
        "opening_balance_imports",
        ["journal_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_opening_balance_imports_onboarding_session_id"),
        "opening_balance_imports",
        ["onboarding_session_id"],
        unique=False,
    )
    op.create_table(
        "opening_balance_lines",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("opening_balance_import_id", sa.Uuid(), nullable=False),
        sa.Column("source_row_key", sa.String(length=300), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_id", sa.Uuid(), nullable=True),
        sa.Column("debit_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("credit_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(debit_amount>0 AND credit_amount=0) OR (credit_amount>0 AND debit_amount=0)",
            name=op.f("ck_opening_balance_lines_amount_side"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            name=op.f("fk_opening_balance_lines_company_id_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "counterparty_id"],
            ["counterparties.company_id", "counterparties.id"],
            name=op.f("fk_opening_balance_lines_company_id_counterparty_id_counterparties"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "opening_balance_import_id"],
            ["opening_balance_imports.company_id", "opening_balance_imports.id"],
            name=op.f(
                "fk_opening_balance_lines_company_id_opening_balance_import_id_opening_balance_imports"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_opening_balance_lines_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opening_balance_lines")),
    )
    op.create_index(
        op.f("ix_opening_balance_lines_account_id"),
        "opening_balance_lines",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opening_balance_lines_company_id"),
        "opening_balance_lines",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opening_balance_lines_counterparty_id"),
        "opening_balance_lines",
        ["counterparty_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opening_balance_lines_opening_balance_import_id"),
        "opening_balance_lines",
        ["opening_balance_import_id"],
        unique=False,
    )

    op.create_index(
        "ix_journal_entries_company_date", "journal_entries", ["company_id", "entry_date", "status"]
    )

    op.create_index(
        "uq_journal_posted_source",
        "journal_entries",
        ["company_id", "source_transaction_id"],
        unique=True,
        postgresql_where=sa.text("status='POSTED' AND source_transaction_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_journal_posted_source", table_name="journal_entries")
    op.drop_index("ix_journal_entries_company_date", table_name="journal_entries")
    # 기초잔액 입력 스냅샷은 전표와 관계형으로 연결합니다.
    op.drop_index(
        op.f("ix_opening_balance_lines_opening_balance_import_id"),
        table_name="opening_balance_lines",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_opening_balance_lines_counterparty_id"),
        table_name="opening_balance_lines",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_opening_balance_lines_company_id"),
        table_name="opening_balance_lines",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_opening_balance_lines_account_id"),
        table_name="opening_balance_lines",
        if_exists=True,
    )
    op.drop_table("opening_balance_lines", if_exists=True)
    op.drop_index(
        op.f("ix_opening_balance_imports_onboarding_session_id"),
        table_name="opening_balance_imports",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_opening_balance_imports_journal_id"),
        table_name="opening_balance_imports",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_opening_balance_imports_created_by"),
        table_name="opening_balance_imports",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_opening_balance_imports_company_id"),
        table_name="opening_balance_imports",
        if_exists=True,
    )
    op.drop_table("opening_balance_imports", if_exists=True)

    # 회사 경계와 복식부기 제약을 명시적으로 생성합니다.
    op.drop_index(op.f("ix_journal_proposals_transaction_id"), table_name="journal_proposals")
    op.drop_index(op.f("ix_journal_proposals_journal_entry_id"), table_name="journal_proposals")
    op.drop_index(op.f("ix_journal_proposals_company_id"), table_name="journal_proposals")
    op.drop_table("journal_proposals")
    op.drop_index(op.f("ix_journal_lines_journal_entry_id"), table_name="journal_lines")
    op.drop_index(op.f("ix_journal_lines_counterparty_id"), table_name="journal_lines")
    op.drop_index(op.f("ix_journal_lines_company_id"), table_name="journal_lines")
    op.drop_index(op.f("ix_journal_lines_account_id"), table_name="journal_lines")
    op.drop_table("journal_lines")
    op.drop_index(op.f("ix_journal_evidences_journal_entry_id"), table_name="journal_evidences")
    op.drop_index(op.f("ix_journal_evidences_evidence_id"), table_name="journal_evidences")
    op.drop_index(op.f("ix_journal_evidences_company_id"), table_name="journal_evidences")
    op.drop_table("journal_evidences")
    op.drop_index(op.f("ix_journal_entries_status"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_source_transaction_id"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_reversal_of_id"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_posted_by"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_entry_date"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_created_by"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_company_id"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_approved_by"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_approval_id"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_accounting_period_id"), table_name="journal_entries")
    op.drop_table("journal_entries")
    op.drop_constraint(
        op.f("uq_accounting_periods_company_id_id"), "accounting_periods", type_="unique"
    )
