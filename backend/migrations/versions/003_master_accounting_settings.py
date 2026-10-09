"""회계 마스터와 회계정책 관계형 기반

리비전: 003_master_accounting_settings
이전 리비전: 002_tenant_company_rbac
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_master_accounting_settings"
down_revision: str | Sequence[str] | None = "002_tenant_company_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # 명시적 테이블과 관계형 제약을 적용합니다.
    op.create_table(
        "coa_templates",
        sa.Column("template_code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','RETIRED')", name=op.f("ck_coa_templates_status")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_coa_templates_version")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coa_templates")),
        sa.UniqueConstraint(
            "template_code", "version", name=op.f("uq_coa_templates_template_code_version")
        ),
    )
    op.create_table(
        "coa_template_accounts",
        sa.Column("coa_template_id", sa.Uuid(), nullable=False),
        sa.Column("account_code", sa.String(length=20), nullable=False),
        sa.Column("account_name", sa.String(length=200), nullable=False),
        sa.Column("account_type", sa.String(length=16), nullable=False),
        sa.Column("normal_balance", sa.String(length=6), nullable=False),
        sa.Column("parent_code", sa.String(length=20), nullable=True),
        sa.Column("posting_allowed", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_contra", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "account_type IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')",
            name=op.f("ck_coa_template_accounts_type"),
        ),
        sa.CheckConstraint(
            (
                "normal_balance = CASE WHEN (account_type IN ('ASSET','EXPENSE')) "
                "<> is_contra THEN 'DEBIT' ELSE 'CREDIT' END"
            ),
            name=op.f("ck_coa_template_accounts_normal_balance"),
        ),
        sa.CheckConstraint(
            "normal_balance IN ('DEBIT','CREDIT')",
            name=op.f("ck_coa_template_accounts_balance_side"),
        ),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_coa_template_accounts_display_order")
        ),
        sa.CheckConstraint(
            "parent_code IS NULL OR parent_code <> account_code",
            name=op.f("ck_coa_template_accounts_parent_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["coa_template_id", "parent_code"],
            ["coa_template_accounts.coa_template_id", "coa_template_accounts.account_code"],
            name=op.f("fk_coa_template_accounts_coa_template_id_parent_code_coa_template_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["coa_template_id"],
            ["coa_templates.id"],
            name=op.f("fk_coa_template_accounts_coa_template_id_coa_templates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coa_template_accounts")),
        sa.UniqueConstraint(
            "coa_template_id",
            "account_code",
            name=op.f("uq_coa_template_accounts_coa_template_id_account_code"),
        ),
    )
    op.create_index(
        op.f("ix_coa_template_accounts_coa_template_id"),
        "coa_template_accounts",
        ["coa_template_id"],
        unique=False,
    )
    op.create_index(
        "ix_coa_template_accounts_parent",
        "coa_template_accounts",
        ["coa_template_id", "parent_code"],
        unique=False,
    )
    op.create_table(
        "accounting_periods",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("period_no", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'OPEN'"), nullable=False),
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
        postgresql.ExcludeConstraint(
            (sa.column("company_id"), "="),
            (sa.text("daterange(start_date, end_date, '[]')"), "&&"),
            using="gist",
            name="ex_accounting_periods_date_range",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','CLOSED')", name=op.f("ck_accounting_periods_status")
        ),
        sa.CheckConstraint(
            "fiscal_year BETWEEN 1900 AND 9998 AND period_no BETWEEN 1 AND 12",
            name=op.f("ck_accounting_periods_period_number"),
        ),
        sa.CheckConstraint("start_date <= end_date", name=op.f("ck_accounting_periods_date_range")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_accounting_periods_version")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_accounting_periods_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_periods")),
        sa.UniqueConstraint(
            "company_id",
            "fiscal_year",
            "period_no",
            name=op.f("uq_accounting_periods_company_id_fiscal_year_period_no"),
        ),
    )
    op.create_index(
        "ix_accounting_periods_company_dates",
        "accounting_periods",
        ["company_id", "start_date", "end_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_accounting_periods_company_id"), "accounting_periods", ["company_id"], unique=False
    )
    op.create_table(
        "accounting_settings",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("functional_currency_code", sa.String(length=3), nullable=False),
        sa.Column("fiscal_year_start_month", sa.Integer(), nullable=False),
        sa.Column("journal_number_prefix", sa.String(length=10), nullable=False),
        sa.Column("numbering_reset_policy", sa.String(length=16), nullable=False),
        sa.Column("allow_manual_journal", sa.Boolean(), nullable=False),
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
            "functional_currency_code IN ('KRW','USD','EUR','JPY','G"
            "BP','CAD','AUD','CHF','CNY','SGD','HKD')",
            name=op.f("ck_accounting_settings_currency"),
        ),
        sa.CheckConstraint(
            "journal_number_prefix ~ '^[A-Z][A-Z0-9]{0,9}$'",
            name=op.f("ck_accounting_settings_prefix"),
        ),
        sa.CheckConstraint(
            "numbering_reset_policy IN ('FISCAL_YEAR','NEVER')",
            name=op.f("ck_accounting_settings_reset_policy"),
        ),
        sa.CheckConstraint(
            "fiscal_year_start_month BETWEEN 1 AND 12",
            name=op.f("ck_accounting_settings_fiscal_month"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_accounting_settings_version")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_accounting_settings_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_settings")),
    )
    op.create_index(
        op.f("ix_accounting_settings_company_id"),
        "accounting_settings",
        ["company_id"],
        unique=True,
    )
    op.create_table(
        "chart_of_accounts",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("template_account_id", sa.Uuid(), nullable=True),
        sa.Column("account_code", sa.String(length=20), nullable=False),
        sa.Column("account_name", sa.String(length=200), nullable=False),
        sa.Column("account_type", sa.String(length=16), nullable=False),
        sa.Column("normal_balance", sa.String(length=6), nullable=False),
        sa.Column("parent_account_id", sa.Uuid(), nullable=True),
        sa.Column("posting_allowed", sa.Boolean(), nullable=False),
        sa.Column("is_contra", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'ACTIVE'"), nullable=False
        ),
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
            "account_type IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')",
            name=op.f("ck_chart_of_accounts_type"),
        ),
        sa.CheckConstraint(
            (
                "normal_balance = CASE WHEN (account_type IN ('ASSET','EXPENSE')) "
                "<> is_contra THEN 'DEBIT' ELSE 'CREDIT' END"
            ),
            name=op.f("ck_chart_of_accounts_normal_balance"),
        ),
        sa.CheckConstraint(
            "normal_balance IN ('DEBIT','CREDIT')", name=op.f("ck_chart_of_accounts_balance_side")
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name=op.f("ck_chart_of_accounts_status")
        ),
        sa.CheckConstraint(
            "parent_account_id IS NULL OR parent_account_id <> id",
            name=op.f("ck_chart_of_accounts_parent_not_self"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_chart_of_accounts_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "parent_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            name=op.f("fk_chart_of_accounts_company_id_parent_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_chart_of_accounts_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_account_id"],
            ["coa_template_accounts.id"],
            name=op.f("fk_chart_of_accounts_template_account_id_coa_template_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chart_of_accounts")),
        sa.UniqueConstraint(
            "company_id", "account_code", name=op.f("uq_chart_of_accounts_company_id_account_code")
        ),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_chart_of_accounts_company_id_id")),
    )
    op.create_index(
        op.f("ix_chart_of_accounts_company_id"), "chart_of_accounts", ["company_id"], unique=False
    )
    op.create_index(
        "ix_chart_of_accounts_parent",
        "chart_of_accounts",
        ["company_id", "parent_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chart_of_accounts_parent_account_id"),
        "chart_of_accounts",
        ["parent_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chart_of_accounts_template_account_id"),
        "chart_of_accounts",
        ["template_account_id"],
        unique=False,
    )
    op.create_table(
        "journal_sequences",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("sequence_key", sa.String(length=40), nullable=False),
        sa.Column("last_number", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "fiscal_year=0 OR fiscal_year BETWEEN 1900 AND 9998",
            name=op.f("ck_journal_sequences_fiscal_year"),
        ),
        sa.CheckConstraint("last_number >= 0", name=op.f("ck_journal_sequences_last_number")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_journal_sequences_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_sequences")),
        sa.UniqueConstraint(
            "company_id",
            "fiscal_year",
            "sequence_key",
            name=op.f("uq_journal_sequences_company_id_fiscal_year_sequence_key"),
        ),
    )
    op.create_index(
        op.f("ix_journal_sequences_company_id"), "journal_sequences", ["company_id"], unique=False
    )
    op.create_table(
        "payment_terms",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("term_code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("due_rule_type", sa.String(length=32), nullable=False),
        sa.Column("due_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "due_days BETWEEN 0 AND 3650 AND (due_rule_type <> 'IMMEDIATE' OR due_days=0)",
            name=op.f("ck_payment_terms_due_days"),
        ),
        sa.CheckConstraint(
            "due_rule_type IN ('IMMEDIATE','NET_DAYS','MONTH_END_PLUS_DAYS')",
            name=op.f("ck_payment_terms_due_rule"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_payment_terms_version")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_payment_terms_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_terms")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_payment_terms_company_id_id")),
        sa.UniqueConstraint(
            "company_id", "term_code", name=op.f("uq_payment_terms_company_id_term_code")
        ),
    )
    op.create_index(
        op.f("ix_payment_terms_company_id"), "payment_terms", ["company_id"], unique=False
    )
    op.create_table(
        "counterparties",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_legal_name", sa.String(length=200), nullable=False),
        sa.Column("business_number", sa.String(length=10), nullable=True),
        sa.Column("corporation_number", sa.String(length=13), nullable=True),
        sa.Column("counterparty_type", sa.String(length=20), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'ACTIVE'"), nullable=False
        ),
        sa.Column("default_currency_code", sa.String(length=3), nullable=False),
        sa.Column("payment_term_id", sa.Uuid(), nullable=True),
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
            "business_number IS NULL OR business_number ~ '^[0-9]{10}$'",
            name=op.f("ck_counterparties_business_number"),
        ),
        sa.CheckConstraint(
            "corporation_number IS NULL OR corporation_number ~ '^[0-9]{13}$'",
            name=op.f("ck_counterparties_corporation_number"),
        ),
        sa.CheckConstraint(
            "counterparty_type IN ('BUSINESS','INDIVIDUAL','OTHER')",
            name=op.f("ck_counterparties_type"),
        ),
        sa.CheckConstraint(
            "default_currency_code IN ('KRW','USD','EUR','JPY','GBP'"
            ",'CAD','AUD','CHF','CNY','SGD','HKD')",
            name=op.f("ck_counterparties_currency"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','BLOCKED')", name=op.f("ck_counterparties_status")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_counterparties_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "payment_term_id"],
            ["payment_terms.company_id", "payment_terms.id"],
            name=op.f("fk_counterparties_company_id_payment_term_id_payment_terms"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_counterparties_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_counterparties")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_counterparties_company_id_id")),
    )
    op.create_index(
        op.f("ix_counterparties_company_id"), "counterparties", ["company_id"], unique=False
    )
    op.create_index(
        "ix_counterparties_company_id_display_name",
        "counterparties",
        ["company_id", "display_name"],
        unique=False,
    )
    op.create_index(
        "ix_counterparties_company_id_normalized_legal_name",
        "counterparties",
        ["company_id", "normalized_legal_name"],
        unique=False,
    )
    op.create_index(
        "ix_counterparties_company_id_payment_term_id",
        "counterparties",
        ["company_id", "payment_term_id"],
        unique=False,
    )
    op.create_index(
        "ix_counterparties_company_id_status",
        "counterparties",
        ["company_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_counterparties_payment_term_id"),
        "counterparties",
        ["payment_term_id"],
        unique=False,
    )
    op.create_index(
        "uq_counterparties_company_business",
        "counterparties",
        ["company_id", "business_number"],
        unique=True,
        postgresql_where=sa.text("business_number IS NOT NULL"),
    )
    op.create_table(
        "counterparty_addresses",
        sa.Column("counterparty_id", sa.Uuid(), nullable=False),
        sa.Column("address_type", sa.String(length=24), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("address_line1", sa.String(length=300), nullable=False),
        sa.Column("address_line2", sa.String(length=300), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "address_type IN ('REGISTERED','BILLING','SHIPPING')",
            name=op.f("ck_counterparty_addresses_type"),
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_id"],
            ["counterparties.id"],
            name=op.f("fk_counterparty_addresses_counterparty_id_counterparties"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_counterparty_addresses")),
    )
    op.create_index(
        op.f("ix_counterparty_addresses_counterparty_id"),
        "counterparty_addresses",
        ["counterparty_id"],
        unique=False,
    )
    op.create_index(
        "uq_counterparty_primary_address",
        "counterparty_addresses",
        ["counterparty_id", "address_type"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_table(
        "counterparty_bank_refs",
        sa.Column("counterparty_id", sa.Uuid(), nullable=False),
        sa.Column("bank_code", sa.String(length=20), nullable=False),
        sa.Column("account_alias", sa.String(length=100), nullable=False),
        sa.Column("external_token", sa.String(length=80), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'ACTIVE'"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "external_token ~ '^vault:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-"
            "f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name=op.f("ck_counterparty_bank_refs_vault_reference"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name=op.f("ck_counterparty_bank_refs_status")
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_id"],
            ["counterparties.id"],
            name=op.f("fk_counterparty_bank_refs_counterparty_id_counterparties"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_counterparty_bank_refs")),
    )
    op.create_index(
        op.f("ix_counterparty_bank_refs_counterparty_id"),
        "counterparty_bank_refs",
        ["counterparty_id"],
        unique=False,
    )
    op.create_table(
        "counterparty_contacts",
        sa.Column("counterparty_id", sa.Uuid(), nullable=False),
        sa.Column("contact_type", sa.String(length=24), nullable=False),
        sa.Column("contact_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "contact_type IN ('GENERAL','BILLING','SALES')",
            name=op.f("ck_counterparty_contacts_type"),
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_id"],
            ["counterparties.id"],
            name=op.f("fk_counterparty_contacts_counterparty_id_counterparties"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_counterparty_contacts")),
    )
    op.create_index(
        op.f("ix_counterparty_contacts_counterparty_id"),
        "counterparty_contacts",
        ["counterparty_id"],
        unique=False,
    )
    op.create_index(
        "uq_counterparty_primary_contact",
        "counterparty_contacts",
        ["counterparty_id", "contact_type"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_table(
        "counterparty_roles",
        sa.Column("counterparty_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.String(length=32), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        postgresql.ExcludeConstraint(
            (sa.column("counterparty_id"), "="),
            (sa.column("role_code"), "="),
            (sa.text("daterange(effective_from, effective_to, '[]')"), "&&"),
            using="gist",
            name="ex_counterparty_role_effective_range",
        ),
        sa.CheckConstraint(
            "role_code IN ('CUSTOMER','SUPPLIER','PAYEE','TAX_COUNTERPARTY')",
            name=op.f("ck_counterparty_roles_role"),
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from <= effective_to",
            name=op.f("ck_counterparty_roles_date_range"),
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_id"],
            ["counterparties.id"],
            name=op.f("fk_counterparty_roles_counterparty_id_counterparties"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_counterparty_roles")),
    )
    op.create_index(
        op.f("ix_counterparty_roles_counterparty_id"),
        "counterparty_roles",
        ["counterparty_id"],
        unique=False,
    )


def downgrade() -> None:
    # 명시적 테이블과 관계형 제약을 적용합니다.
    op.drop_index(op.f("ix_counterparty_roles_counterparty_id"), table_name="counterparty_roles")
    op.drop_table("counterparty_roles")
    op.drop_index(
        "uq_counterparty_primary_contact",
        table_name="counterparty_contacts",
        postgresql_where=sa.text("is_primary"),
    )
    op.drop_index(
        op.f("ix_counterparty_contacts_counterparty_id"), table_name="counterparty_contacts"
    )
    op.drop_table("counterparty_contacts")
    op.drop_index(
        op.f("ix_counterparty_bank_refs_counterparty_id"), table_name="counterparty_bank_refs"
    )
    op.drop_table("counterparty_bank_refs")
    op.drop_index(
        "uq_counterparty_primary_address",
        table_name="counterparty_addresses",
        postgresql_where=sa.text("is_primary"),
    )
    op.drop_index(
        op.f("ix_counterparty_addresses_counterparty_id"), table_name="counterparty_addresses"
    )
    op.drop_table("counterparty_addresses")
    op.drop_index(
        "uq_counterparties_company_business",
        table_name="counterparties",
        postgresql_where=sa.text("business_number IS NOT NULL"),
    )
    op.drop_index(op.f("ix_counterparties_payment_term_id"), table_name="counterparties")
    op.drop_index("ix_counterparties_company_id_status", table_name="counterparties")
    op.drop_index("ix_counterparties_company_id_payment_term_id", table_name="counterparties")
    op.drop_index("ix_counterparties_company_id_normalized_legal_name", table_name="counterparties")
    op.drop_index("ix_counterparties_company_id_display_name", table_name="counterparties")
    op.drop_index(op.f("ix_counterparties_company_id"), table_name="counterparties")
    op.drop_table("counterparties")
    op.drop_index(op.f("ix_payment_terms_company_id"), table_name="payment_terms")
    op.drop_table("payment_terms")
    op.drop_index(op.f("ix_journal_sequences_company_id"), table_name="journal_sequences")
    op.drop_table("journal_sequences")
    op.drop_index(op.f("ix_chart_of_accounts_template_account_id"), table_name="chart_of_accounts")
    op.drop_index(op.f("ix_chart_of_accounts_parent_account_id"), table_name="chart_of_accounts")
    op.drop_index("ix_chart_of_accounts_parent", table_name="chart_of_accounts")
    op.drop_index(op.f("ix_chart_of_accounts_company_id"), table_name="chart_of_accounts")
    op.drop_table("chart_of_accounts")
    op.drop_index(op.f("ix_accounting_settings_company_id"), table_name="accounting_settings")
    op.drop_table("accounting_settings")
    op.drop_index(op.f("ix_accounting_periods_company_id"), table_name="accounting_periods")
    op.drop_index("ix_accounting_periods_company_dates", table_name="accounting_periods")
    op.drop_table("accounting_periods")
    op.drop_index("ix_coa_template_accounts_parent", table_name="coa_template_accounts")
    op.drop_index(
        op.f("ix_coa_template_accounts_coa_template_id"), table_name="coa_template_accounts"
    )
    op.drop_table("coa_template_accounts")
    op.drop_table("coa_templates")
