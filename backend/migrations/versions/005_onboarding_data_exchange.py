"""온보딩 초안과 데이터 병합 기반

리비전: 005_onboarding_data_exchange
이전 리비전: 004_storage_evidence_intake
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_onboarding_data_exchange"
down_revision: str | Sequence[str] | None = "004_storage_evidence_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_import_sheets_dimensions"), "import_sheets", type_="check")
    op.create_check_constraint(
        op.f("ck_import_sheets_dimensions"),
        "import_sheets",
        "sheet_index >= 0 AND row_count BETWEEN 0 AND 1000 AND column_count BETWEEN 1 AND 40",
    )
    op.add_column("counterparties", sa.Column("counterparty_code", sa.String(80), nullable=True))
    op.create_unique_constraint(
        op.f("uq_counterparties_company_id_counterparty_code"),
        "counterparties",
        ["company_id", "counterparty_code"],
    )
    op.drop_constraint(op.f("ck_imports_sheets"), "imports", type_="check")
    op.create_check_constraint(op.f("ck_imports_sheets"), "imports", "sheet_count BETWEEN 1 AND 16")
    op.drop_constraint(op.f("ck_imports_source"), "imports", type_="check")
    op.create_check_constraint(
        op.f("ck_imports_source"),
        "imports",
        "source_type IN ('BANK_TRANSACTION','CARD_TRANSACTION','SALES',"
        "'PURCHASE','EXPENSE','OPENING_BALANCE','COUNTERPARTY','ONBOARDING_TEMPLATE')",
    )
    # 관계형 제약과 외래키 순서를 명시적으로 유지합니다.
    op.create_table(
        "onboarding_field_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("field_code", sa.String(length=100), nullable=False),
        sa.Column("section_code", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("data_type", sa.String(length=12), nullable=False),
        sa.Column("input_mode", sa.String(length=24), nullable=False),
        sa.Column("required_rule_code", sa.String(length=32), nullable=False),
        sa.Column("enum_source_code", sa.String(length=40), nullable=True),
        sa.Column("derived_handler_key", sa.String(length=40), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "data_type IN ('TEXT','NUMERIC','DATE','BOOLEAN')",
            name=op.f("ck_onboarding_field_definitions_data_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_field_definitions")),
        sa.UniqueConstraint("field_code", name=op.f("uq_onboarding_field_definitions_field_code")),
        sa.UniqueConstraint(
            "id", "section_code", name=op.f("uq_onboarding_field_definitions_id_section_code")
        ),
    )
    op.create_table(
        "onboarding_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_step", sa.String(length=40), nullable=False),
        sa.Column("started_by", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED','IN_PROGRESS','REVIEW_REQUIRED',"
            "'READY_TO_COMPLETE','COMPLETED')",
            name=op.f("ck_onboarding_sessions_status"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_onboarding_sessions_version")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_onboarding_sessions_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["started_by"],
            ["users.id"],
            name=op.f("fk_onboarding_sessions_started_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_sessions")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_onboarding_sessions_company_id_id")),
        sa.UniqueConstraint("company_id", name=op.f("uq_onboarding_sessions_company_id")),
    )
    op.create_index(
        op.f("ix_onboarding_sessions_company_id"),
        "onboarding_sessions",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_sessions_started_by"),
        "onboarding_sessions",
        ["started_by"],
        unique=False,
    )
    op.create_table(
        "onboarding_promotion_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("account_count", sa.Integer(), nullable=False),
        sa.Column("counterparty_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            name=op.f("fk_onboarding_promotion_receipts_company_id_session_id_onboarding_sessions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_promotion_receipts")),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name=op.f("uq_onboarding_promotion_receipts_company_id_idempotency_key"),
        ),
        sa.UniqueConstraint("session_id", name=op.f("uq_onboarding_promotion_receipts_session_id")),
    )
    op.create_index(
        op.f("ix_onboarding_promotion_receipts_company_id"),
        "onboarding_promotion_receipts",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_promotion_receipts_session_id"),
        "onboarding_promotion_receipts",
        ["session_id"],
        unique=False,
    )
    op.create_table(
        "onboarding_row_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("section_code", sa.String(length=40), nullable=False),
        sa.Column("row_key", sa.String(length=260), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            name=op.f("fk_onboarding_row_items_company_id_session_id_onboarding_sessions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_row_items")),
        sa.UniqueConstraint(
            "session_id",
            "section_code",
            "row_key",
            name=op.f("uq_onboarding_row_items_session_id_section_code_row_key"),
        ),
    )
    op.create_index(
        op.f("ix_onboarding_row_items_company_id"),
        "onboarding_row_items",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_row_items_session_id"),
        "onboarding_row_items",
        ["session_id"],
        unique=False,
    )
    op.create_table(
        "onboarding_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("section_code", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            name=op.f("fk_onboarding_sections_company_id_session_id_onboarding_sessions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_sections")),
        sa.UniqueConstraint(
            "session_id",
            "section_code",
            name=op.f("uq_onboarding_sections_session_id_section_code"),
        ),
    )
    op.create_index(
        op.f("ix_onboarding_sections_company_id"),
        "onboarding_sections",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_sections_session_id"),
        "onboarding_sections",
        ["session_id"],
        unique=False,
    )
    op.create_table(
        "onboarding_validation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("field_definition_id", sa.Uuid(), nullable=True),
        sa.Column("row_key", sa.String(length=260), nullable=False),
        sa.Column("validation_code", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            name=op.f("fk_onboarding_validation_results_company_id_session_id_onboarding_sessions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["field_definition_id"],
            ["onboarding_field_definitions.id"],
            name=op.f(
                "fk_onboarding_validation_results_field_definition_id_onboarding_field_definitions"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_validation_results")),
    )
    op.create_index(
        op.f("ix_onboarding_validation_results_company_id"),
        "onboarding_validation_results",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_validation_results_field_definition_id"),
        "onboarding_validation_results",
        ["field_definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_validation_results_session_id"),
        "onboarding_validation_results",
        ["session_id"],
        unique=False,
    )
    op.create_table(
        "onboarding_apply_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("new_count", sa.Integer(), nullable=False),
        sa.Column("changed_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("conflict_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_onboarding_apply_receipts_company_id_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            name=op.f("fk_onboarding_apply_receipts_company_id_session_id_onboarding_sessions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_apply_receipts")),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name=op.f("uq_onboarding_apply_receipts_company_id_idempotency_key"),
        ),
        sa.UniqueConstraint("import_id", name=op.f("uq_onboarding_apply_receipts_import_id")),
    )
    op.create_index(
        op.f("ix_onboarding_apply_receipts_company_id"),
        "onboarding_apply_receipts",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_apply_receipts_import_id"),
        "onboarding_apply_receipts",
        ["import_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_apply_receipts_session_id"),
        "onboarding_apply_receipts",
        ["session_id"],
        unique=False,
    )
    op.create_table(
        "onboarding_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("template_code", sa.String(length=40), nullable=False),
        sa.Column("template_version", sa.String(length=16), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_onboarding_imports_company_id_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            name=op.f("fk_onboarding_imports_company_id_session_id_onboarding_sessions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_imports")),
        sa.UniqueConstraint("import_id", name=op.f("uq_onboarding_imports_import_id")),
    )
    op.create_index(
        op.f("ix_onboarding_imports_company_id"), "onboarding_imports", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_onboarding_imports_import_id"), "onboarding_imports", ["import_id"], unique=False
    )
    op.create_index(
        op.f("ix_onboarding_imports_session_id"), "onboarding_imports", ["session_id"], unique=False
    )
    op.create_table(
        "onboarding_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("field_definition_id", sa.Uuid(), nullable=False),
        sa.Column("section_code", sa.String(length=40), nullable=False),
        sa.Column("row_key", sa.String(length=260), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("value_text", sa.String(length=500), nullable=True),
        sa.Column(
            "value_numeric",
            sa.Numeric(precision=19, scale=4),
            nullable=True,
        ),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_import_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "source_type != 'EXCEL_IMPORT' OR source_import_id IS NOT NULL",
            name=op.f("ck_onboarding_values_source_reference"),
        ),
        sa.CheckConstraint(
            "source_type IN ('MANUAL','EXCEL_IMPORT','SYSTEM_DEFAULT','DERIVED')",
            name=op.f("ck_onboarding_values_source_type"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','VALID','INVALID','STALE')",
            name=op.f("ck_onboarding_values_status"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(value_text,value_numeric,value_date,value_boolean) = 1",
            name=op.f("ck_onboarding_values_one_typed_value"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_onboarding_values_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            name=op.f("fk_onboarding_values_company_id_session_id_onboarding_sessions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_onboarding_values_company_id_source_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["field_definition_id", "section_code"],
            ["onboarding_field_definitions.id", "onboarding_field_definitions.section_code"],
            name=op.f(
                "fk_onboarding_values_field_definition_id_section_code_onboarding_field_definitions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "section_code", "row_key"],
            [
                "onboarding_row_items.session_id",
                "onboarding_row_items.section_code",
                "onboarding_row_items.row_key",
            ],
            name=op.f("fk_onboarding_values_session_id_section_code_row_key_onboarding_row_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_onboarding_values_updated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_values")),
        sa.UniqueConstraint(
            "session_id",
            "field_definition_id",
            "row_key",
            name=op.f("uq_onboarding_values_session_id_field_definition_id_row_key"),
        ),
    )
    op.create_index(
        op.f("ix_onboarding_values_company_id"), "onboarding_values", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_onboarding_values_field_definition_id"),
        "onboarding_values",
        ["field_definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_values_session_id"), "onboarding_values", ["session_id"], unique=False
    )
    op.create_index(
        op.f("ix_onboarding_values_source_import_id"),
        "onboarding_values",
        ["source_import_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_values_updated_by"), "onboarding_values", ["updated_by"], unique=False
    )
    op.create_table(
        "onboarding_value_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("value_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("value_text", sa.String(length=500), nullable=True),
        sa.Column(
            "value_numeric",
            sa.Numeric(precision=19, scale=4),
            nullable=True,
        ),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_import_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(value_text,value_numeric,value_date,value_boolean) = 1",
            name=op.f("ck_onboarding_value_history_one_typed_value"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["onboarding_sessions.company_id", "onboarding_sessions.id"],
            name=op.f("fk_onboarding_value_history_company_id_session_id_onboarding_sessions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_onboarding_value_history_company_id_source_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_onboarding_value_history_updated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["value_id"],
            ["onboarding_values.id"],
            name=op.f("fk_onboarding_value_history_value_id_onboarding_values"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_value_history")),
        sa.UniqueConstraint(
            "value_id", "version", name=op.f("uq_onboarding_value_history_value_id_version")
        ),
    )
    op.create_index(
        op.f("ix_onboarding_value_history_company_id"),
        "onboarding_value_history",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_value_history_session_id"),
        "onboarding_value_history",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_value_history_source_import_id"),
        "onboarding_value_history",
        ["source_import_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_value_history_updated_by"),
        "onboarding_value_history",
        ["updated_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_onboarding_value_history_value_id"),
        "onboarding_value_history",
        ["value_id"],
        unique=False,
    )
    op.add_column(
        "accounting_settings",
        sa.Column(
            "accounting_framework_code",
            sa.String(length=20),
            server_default="K_GAAP",
            nullable=False,
        ),
    )
    op.add_column(
        "accounting_settings",
        sa.Column(
            "reporting_taxonomy_code",
            sa.String(length=20),
            server_default="STANDARD",
            nullable=False,
        ),
    )
    op.add_column(
        "companies",
        sa.Column("timezone", sa.String(length=40), server_default="Asia/Seoul", nullable=False),
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_import_sheets_dimensions"), "import_sheets", type_="check")
    op.create_check_constraint(
        op.f("ck_import_sheets_dimensions"),
        "import_sheets",
        "sheet_index >= 0 AND row_count BETWEEN 1 AND 1000 AND column_count BETWEEN 1 AND 40",
    )
    op.drop_constraint(
        op.f("uq_counterparties_company_id_counterparty_code"), "counterparties", type_="unique"
    )
    op.drop_column("counterparties", "counterparty_code")
    # 온보딩 파일이 남아 있으면 downgrade는 보존 정책에 따라 거부됩니다.
    op.drop_constraint(op.f("ck_imports_sheets"), "imports", type_="check")
    op.create_check_constraint(op.f("ck_imports_sheets"), "imports", "sheet_count BETWEEN 1 AND 5")
    op.drop_constraint(op.f("ck_imports_source"), "imports", type_="check")
    op.create_check_constraint(
        op.f("ck_imports_source"),
        "imports",
        "source_type IN ('BANK_TRANSACTION','CARD_TRANSACTION','SALES',"
        "'PURCHASE','EXPENSE','OPENING_BALANCE','COUNTERPARTY')",
    )
    # 관계형 제약과 외래키 순서를 명시적으로 유지합니다.
    op.drop_column("companies", "timezone")
    op.drop_column("accounting_settings", "reporting_taxonomy_code")
    op.drop_column("accounting_settings", "accounting_framework_code")
    op.drop_index(
        op.f("ix_onboarding_value_history_value_id"), table_name="onboarding_value_history"
    )
    op.drop_index(
        op.f("ix_onboarding_value_history_updated_by"), table_name="onboarding_value_history"
    )
    op.drop_index(
        op.f("ix_onboarding_value_history_source_import_id"), table_name="onboarding_value_history"
    )
    op.drop_index(
        op.f("ix_onboarding_value_history_session_id"), table_name="onboarding_value_history"
    )
    op.drop_index(
        op.f("ix_onboarding_value_history_company_id"), table_name="onboarding_value_history"
    )
    op.drop_table("onboarding_value_history")
    op.drop_index(op.f("ix_onboarding_values_updated_by"), table_name="onboarding_values")
    op.drop_index(op.f("ix_onboarding_values_source_import_id"), table_name="onboarding_values")
    op.drop_index(op.f("ix_onboarding_values_session_id"), table_name="onboarding_values")
    op.drop_index(op.f("ix_onboarding_values_field_definition_id"), table_name="onboarding_values")
    op.drop_index(op.f("ix_onboarding_values_company_id"), table_name="onboarding_values")
    op.drop_table("onboarding_values")
    op.drop_index(op.f("ix_onboarding_imports_session_id"), table_name="onboarding_imports")
    op.drop_index(op.f("ix_onboarding_imports_import_id"), table_name="onboarding_imports")
    op.drop_index(op.f("ix_onboarding_imports_company_id"), table_name="onboarding_imports")
    op.drop_table("onboarding_imports")
    op.drop_index(
        op.f("ix_onboarding_apply_receipts_session_id"), table_name="onboarding_apply_receipts"
    )
    op.drop_index(
        op.f("ix_onboarding_apply_receipts_import_id"), table_name="onboarding_apply_receipts"
    )
    op.drop_index(
        op.f("ix_onboarding_apply_receipts_company_id"), table_name="onboarding_apply_receipts"
    )
    op.drop_table("onboarding_apply_receipts")
    op.drop_index(
        op.f("ix_onboarding_validation_results_session_id"),
        table_name="onboarding_validation_results",
    )
    op.drop_index(
        op.f("ix_onboarding_validation_results_field_definition_id"),
        table_name="onboarding_validation_results",
    )
    op.drop_index(
        op.f("ix_onboarding_validation_results_company_id"),
        table_name="onboarding_validation_results",
    )
    op.drop_table("onboarding_validation_results")
    op.drop_index(op.f("ix_onboarding_sections_session_id"), table_name="onboarding_sections")
    op.drop_index(op.f("ix_onboarding_sections_company_id"), table_name="onboarding_sections")
    op.drop_table("onboarding_sections")
    op.drop_index(op.f("ix_onboarding_row_items_session_id"), table_name="onboarding_row_items")
    op.drop_index(op.f("ix_onboarding_row_items_company_id"), table_name="onboarding_row_items")
    op.drop_table("onboarding_row_items")
    op.drop_index(
        op.f("ix_onboarding_promotion_receipts_session_id"),
        table_name="onboarding_promotion_receipts",
    )
    op.drop_index(
        op.f("ix_onboarding_promotion_receipts_company_id"),
        table_name="onboarding_promotion_receipts",
    )
    op.drop_table("onboarding_promotion_receipts")
    op.drop_index(op.f("ix_onboarding_sessions_started_by"), table_name="onboarding_sessions")
    op.drop_index(op.f("ix_onboarding_sessions_company_id"), table_name="onboarding_sessions")
    op.drop_table("onboarding_sessions")
    op.drop_table("onboarding_field_definitions")
