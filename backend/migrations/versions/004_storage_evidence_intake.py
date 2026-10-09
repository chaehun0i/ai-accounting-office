"""파일 증빙과 데이터 인테이크 관계형 기반

리비전: 004_storage_evidence_intake
이전 리비전: 003_master_accounting_settings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_storage_evidence_intake"
down_revision: str | Sequence[str] | None = "003_master_accounting_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 명시적 테이블과 복합 외래키를 생성합니다.
    op.create_table(
        "storage_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("storage_provider", sa.String(length=30), nullable=False),
        sa.Column("storage_key", sa.String(length=100), nullable=False),
        sa.Column("original_filename", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_storage_objects_sha256")),
        sa.CheckConstraint(
            "status IN ('AVAILABLE','RETAINED','DELETED')", name=op.f("ck_storage_objects_status")
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 2000000", name=op.f("ck_storage_objects_size")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_storage_objects_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_storage_objects_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_objects")),
        sa.UniqueConstraint(
            "company_id", "id", "sha256", name=op.f("uq_storage_objects_company_id_id_sha256")
        ),
        sa.UniqueConstraint(
            "storage_provider",
            "storage_key",
            name=op.f("uq_storage_objects_storage_provider_storage_key"),
        ),
    )
    op.create_index(
        op.f("ix_storage_objects_company_id"), "storage_objects", ["company_id"], unique=False
    )
    op.create_index(op.f("ix_storage_objects_sha256"), "storage_objects", ["sha256"], unique=False)
    op.create_table(
        "evidences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=30), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("storage_object_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("original_filename", sa.String(length=200), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("parent_evidence_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "evidence_type IN ('FILE','IMAGE','RECEIPT','TAX_INVOICE','BANK_STATEMENT','CARD_STATEMENT','CONTRACT','EMAIL_REFERENCE','IMPORT_ROW','SYSTEM_FACT','RULE_RESULT','HISTORICAL_JOURNAL')",  # noqa: E501
            name=op.f("ck_evidences_type"),
        ),
        sa.CheckConstraint(
            "parent_evidence_id IS NULL OR parent_evidence_id <> id",
            name=op.f("ck_evidences_parent"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "parent_evidence_id"],
            ["evidences.company_id", "evidences.id"],
            name=op.f("fk_evidences_company_id_parent_evidence_id_evidences"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "storage_object_id", "sha256"],
            ["storage_objects.company_id", "storage_objects.id", "storage_objects.sha256"],
            name=op.f("fk_evidences_company_id_storage_object_id_sha256_storage_objects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_evidences_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_evidences_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidences")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_evidences_company_id_id")),
    )
    op.create_index(op.f("ix_evidences_company_id"), "evidences", ["company_id"], unique=False)
    op.create_index(
        op.f("ix_evidences_parent_evidence_id"), "evidences", ["parent_evidence_id"], unique=False
    )
    op.create_index(
        op.f("ix_evidences_storage_object_id"), "evidences", ["storage_object_id"], unique=False
    )
    op.create_table(
        "imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("target_context", sa.String(length=30), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("storage_object_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=200), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("detected_encoding", sa.String(length=20), nullable=False),
        sa.Column("sheet_count", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("preview_digest", sa.String(length=64), nullable=True),
        sa.Column("preview_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("mapping_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_type IN ('BANK_TRANSACTION','CARD_TRANSACTION','SALES','PURCHASE','EXPENSE','OPENING_BALANCE','COUNTERPARTY')",  # noqa: E501
            name=op.f("ck_imports_source"),
        ),
        sa.CheckConstraint(
            "status IN ('UPLOADED','PARSING','MAPPING_REQUIRED','VALIDATING','PREVIEW_READY','CONFIRMED','IMPORTING','COMPLETED','FAILED','CANCELLED')",  # noqa: E501
            name=op.f("ck_imports_status"),
        ),
        sa.CheckConstraint(
            "target_context IN ('TRANSACTION_CANONICAL','ONBOARDING_DRAFT','DOMAIN_MASTER')",
            name=op.f("ck_imports_target"),
        ),
        sa.CheckConstraint("sheet_count BETWEEN 1 AND 5", name=op.f("ck_imports_sheets")),
        sa.CheckConstraint(
            "version >= 1 AND mapping_version >= 1", name=op.f("ck_imports_versions")
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "storage_object_id", "file_sha256"],
            ["storage_objects.company_id", "storage_objects.id", "storage_objects.sha256"],
            name=op.f("fk_imports_company_id_storage_object_id_file_sha256_storage_objects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_imports_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_imports_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imports")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_imports_company_id_id")),
    )
    op.create_index(op.f("ix_imports_company_id"), "imports", ["company_id"], unique=False)
    op.create_index(
        op.f("ix_imports_storage_object_id"), "imports", ["storage_object_id"], unique=False
    )
    op.create_table(
        "import_evidences",
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            name=op.f("fk_import_evidences_company_id_evidence_id_evidences"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_import_evidences_company_id_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_import_evidences_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("import_id", "evidence_id", name=op.f("pk_import_evidences")),
    )
    op.create_index(
        op.f("ix_import_evidences_company_id"), "import_evidences", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_import_evidences_evidence_id"), "import_evidences", ["evidence_id"], unique=False
    )
    op.create_table(
        "import_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("transaction_count", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("counterparty_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transaction_count = 0 AND counterparty_count = 0 AND evidence_count >= 1",
            name=op.f("ck_import_receipts_counts"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_import_receipts_company_id_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_import_receipts_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_receipts")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_import_receipts_company_id_id")),
        sa.UniqueConstraint("import_id", name=op.f("uq_import_receipts_import_id")),
    )
    op.create_index(
        op.f("ix_import_receipts_company_id"), "import_receipts", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_import_receipts_import_id"), "import_receipts", ["import_id"], unique=False
    )
    op.create_table(
        "import_sheets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("sheet_index", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(length=100), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.CheckConstraint(
            "sheet_index >= 0 AND row_count BETWEEN 1 AND 1000 AND column_count BETWEEN 1 AND 40",
            name=op.f("ck_import_sheets_dimensions"),
        ),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["imports.id"],
            name=op.f("fk_import_sheets_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_sheets")),
        sa.UniqueConstraint("import_id", "id", name=op.f("uq_import_sheets_import_id_id")),
        sa.UniqueConstraint(
            "import_id", "sheet_index", name=op.f("uq_import_sheets_import_id_sheet_index")
        ),
    )
    op.create_index(
        op.f("ix_import_sheets_import_id"), "import_sheets", ["import_id"], unique=False
    )
    op.create_table(
        "import_columns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_sheet_id", sa.Uuid(), nullable=False),
        sa.Column("column_index", sa.Integer(), nullable=False),
        sa.Column("source_header", sa.String(length=100), nullable=False),
        sa.Column("normalized_header", sa.String(length=100), nullable=False),
        sa.Column("detected_type", sa.String(length=30), nullable=False),
        sa.Column("sample_summary", sa.String(length=100), nullable=False),
        sa.Column("is_required_candidate", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "column_index BETWEEN 0 AND 39", name=op.f("ck_import_columns_column_index")
        ),
        sa.ForeignKeyConstraint(
            ["import_sheet_id"],
            ["import_sheets.id"],
            name=op.f("fk_import_columns_import_sheet_id_import_sheets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_columns")),
        sa.UniqueConstraint(
            "import_sheet_id",
            "column_index",
            name=op.f("uq_import_columns_import_sheet_id_column_index"),
        ),
        sa.UniqueConstraint(
            "import_sheet_id", "id", name=op.f("uq_import_columns_import_sheet_id_id")
        ),
    )
    op.create_index(
        op.f("ix_import_columns_import_sheet_id"),
        "import_columns",
        ["import_sheet_id"],
        unique=False,
    )
    op.create_table(
        "import_confirmations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_import_confirmations_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_import_confirmations_company_id_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            ["import_receipts.company_id", "import_receipts.id"],
            name=op.f("fk_import_confirmations_company_id_receipt_id_import_receipts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_import_confirmations_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_confirmations")),
        sa.UniqueConstraint(
            "company_id",
            "actor_id",
            "idempotency_key",
            name=op.f("uq_import_confirmations_company_id_actor_id_idempotency_key"),
        ),
    )
    op.create_index(
        op.f("ix_import_confirmations_company_id"),
        "import_confirmations",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_confirmations_import_id"),
        "import_confirmations",
        ["import_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_confirmations_receipt_id"),
        "import_confirmations",
        ["receipt_id"],
        unique=False,
    )
    op.create_table(
        "import_source_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("target_context", sa.String(length=30), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            ["import_receipts.company_id", "import_receipts.id"],
            name=op.f("fk_import_source_records_company_id_receipt_id_import_receipts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_import_source_records_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_source_records")),
        sa.UniqueConstraint(
            "company_id",
            "source_type",
            "target_context",
            "source_system",
            "source_id",
            name=op.f(
                "uq_import_source_records_company_id_source_type_target_context_source_system_source_id"  # noqa: E501
            ),
        ),
    )
    op.create_index(
        op.f("ix_import_source_records_company_id"),
        "import_source_records",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_source_records_receipt_id"),
        "import_source_records",
        ["receipt_id"],
        unique=False,
    )
    op.create_table(
        "import_validation_errors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("import_sheet_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("column_index", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("message", sa.String(length=200), nullable=False),
        sa.Column("canonical_field_code", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "severity IN ('ERROR','WARNING')", name=op.f("ck_import_validation_errors_severity")
        ),
        sa.CheckConstraint(
            "row_number >= 1 AND column_index >= 0",
            name=op.f("ck_import_validation_errors_locator"),
        ),
        sa.ForeignKeyConstraint(
            ["import_id", "import_sheet_id"],
            ["import_sheets.import_id", "import_sheets.id"],
            name=op.f("fk_import_validation_errors_import_id_import_sheet_id_import_sheets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["imports.id"],
            name=op.f("fk_import_validation_errors_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_validation_errors")),
    )
    op.create_index(
        op.f("ix_import_validation_errors_import_id"),
        "import_validation_errors",
        ["import_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_validation_errors_import_sheet_id"),
        "import_validation_errors",
        ["import_sheet_id"],
        unique=False,
    )
    op.create_table(
        "import_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("import_sheet_id", sa.Uuid(), nullable=False),
        sa.Column("source_column_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_field_code", sa.String(length=50), nullable=True),
        sa.Column("mapping_status", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mapping_status IN ('EXACT','ALIAS_MATCH','AMBIGUOUS','UNMAPPED','USER_CONFIRMED')",
            name=op.f("ck_import_mappings_status"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name=op.f("ck_import_mappings_confidence")
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
            name=op.f("fk_import_mappings_confirmed_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_id", "import_sheet_id"],
            ["import_sheets.import_id", "import_sheets.id"],
            name=op.f("fk_import_mappings_import_id_import_sheet_id_import_sheets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["imports.id"],
            name=op.f("fk_import_mappings_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_sheet_id", "source_column_id"],
            ["import_columns.import_sheet_id", "import_columns.id"],
            name=op.f("fk_import_mappings_import_sheet_id_source_column_id_import_columns"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_mappings")),
        sa.UniqueConstraint(
            "import_sheet_id",
            "canonical_field_code",
            name=op.f("uq_import_mappings_import_sheet_id_canonical_field_code"),
        ),
        sa.UniqueConstraint("source_column_id", name=op.f("uq_import_mappings_source_column_id")),
    )
    op.create_index(
        op.f("ix_import_mappings_import_id"), "import_mappings", ["import_id"], unique=False
    )
    op.create_index(
        op.f("ix_import_mappings_import_sheet_id"),
        "import_mappings",
        ["import_sheet_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_mappings_source_column_id"),
        "import_mappings",
        ["source_column_id"],
        unique=False,
    )


def downgrade() -> None:
    # 명시적 테이블과 복합 외래키를 생성합니다.
    op.drop_index(op.f("ix_import_mappings_source_column_id"), table_name="import_mappings")
    op.drop_index(op.f("ix_import_mappings_import_sheet_id"), table_name="import_mappings")
    op.drop_index(op.f("ix_import_mappings_import_id"), table_name="import_mappings")
    op.drop_table("import_mappings")
    op.drop_index(
        op.f("ix_import_validation_errors_import_sheet_id"), table_name="import_validation_errors"
    )
    op.drop_index(
        op.f("ix_import_validation_errors_import_id"), table_name="import_validation_errors"
    )
    op.drop_table("import_validation_errors")
    op.drop_index(op.f("ix_import_source_records_receipt_id"), table_name="import_source_records")
    op.drop_index(op.f("ix_import_source_records_company_id"), table_name="import_source_records")
    op.drop_table("import_source_records")
    op.drop_index(op.f("ix_import_confirmations_receipt_id"), table_name="import_confirmations")
    op.drop_index(op.f("ix_import_confirmations_import_id"), table_name="import_confirmations")
    op.drop_index(op.f("ix_import_confirmations_company_id"), table_name="import_confirmations")
    op.drop_table("import_confirmations")
    op.drop_index(op.f("ix_import_columns_import_sheet_id"), table_name="import_columns")
    op.drop_table("import_columns")
    op.drop_index(op.f("ix_import_sheets_import_id"), table_name="import_sheets")
    op.drop_table("import_sheets")
    op.drop_index(op.f("ix_import_receipts_import_id"), table_name="import_receipts")
    op.drop_index(op.f("ix_import_receipts_company_id"), table_name="import_receipts")
    op.drop_table("import_receipts")
    op.drop_index(op.f("ix_import_evidences_evidence_id"), table_name="import_evidences")
    op.drop_index(op.f("ix_import_evidences_company_id"), table_name="import_evidences")
    op.drop_table("import_evidences")
    op.drop_index(op.f("ix_imports_storage_object_id"), table_name="imports")
    op.drop_index(op.f("ix_imports_company_id"), table_name="imports")
    op.drop_table("imports")
    op.drop_index(op.f("ix_evidences_storage_object_id"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_parent_evidence_id"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_company_id"), table_name="evidences")
    op.drop_table("evidences")
    op.drop_index(op.f("ix_storage_objects_sha256"), table_name="storage_objects")
    op.drop_index(op.f("ix_storage_objects_company_id"), table_name="storage_objects")
    op.drop_table("storage_objects")
