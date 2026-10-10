"""원본 행은 저장하지 않고 파일·매핑·오류 위치·확정 참조만 보관합니다."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.intake.domain.canonical_fields import SourceType, TargetContext


class ImportModel(Base):
    __tablename__ = "imports"
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        ForeignKeyConstraint(
            ["company_id", "storage_object_id", "file_sha256"],
            ["storage_objects.company_id", "storage_objects.id", "storage_objects.sha256"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1 AND mapping_version >= 1", name="versions"),
        CheckConstraint("sheet_count BETWEEN 1 AND 16", name="sheets"),
        CheckConstraint(
            "source_type IN (" + ",".join(repr(s.value) for s in SourceType) + ")", name="source"
        ),
        CheckConstraint(
            "target_context IN (" + ",".join(repr(s.value) for s in TargetContext) + ")",
            name="target",
        ),
        CheckConstraint(
            "status IN ('UPLOADED','PARSING','MAPPING_REQUIRED','VALIDATING','PREVIEW_READY','CONFIRMED','IMPORTING','COMPLETED','FAILED','CANCELLED')",  # noqa: E501
            name="status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(30))
    target_context: Mapped[str] = mapped_column(String(30))
    source_system: Mapped[str] = mapped_column(String(80))
    storage_object_id: Mapped[UUID] = mapped_column(index=True)
    original_filename: Mapped[str] = mapped_column(String(200))
    file_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30))
    detected_encoding: Mapped[str] = mapped_column(String(20))
    sheet_count: Mapped[int]
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    preview_digest: Mapped[str | None] = mapped_column(String(64))
    preview_expires_at: Mapped[datetime | None]
    version: Mapped[int]
    mapping_version: Mapped[int]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    confirmed_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]


class ImportSheetModel(Base):
    __tablename__ = "import_sheets"
    __table_args__ = (
        UniqueConstraint("import_id", "sheet_index"),
        UniqueConstraint("import_id", "id"),
        CheckConstraint(
            "sheet_index >= 0 AND row_count BETWEEN 0 AND 1000 AND column_count BETWEEN 1 AND 40",
            name="dimensions",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("imports.id", ondelete="RESTRICT"), index=True
    )
    sheet_index: Mapped[int]
    sheet_name: Mapped[str] = mapped_column(String(100))
    row_count: Mapped[int]
    column_count: Mapped[int]
    status: Mapped[str] = mapped_column(String(30))


class ImportColumnModel(Base):
    __tablename__ = "import_columns"
    __table_args__ = (
        UniqueConstraint("import_sheet_id", "column_index"),
        UniqueConstraint("import_sheet_id", "id"),
        CheckConstraint("column_index BETWEEN 0 AND 39", name="column_index"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    import_sheet_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_sheets.id", ondelete="RESTRICT"), index=True
    )
    column_index: Mapped[int]
    source_header: Mapped[str] = mapped_column(String(100))
    normalized_header: Mapped[str] = mapped_column(String(100))
    detected_type: Mapped[str] = mapped_column(String(30))
    sample_summary: Mapped[str] = mapped_column(String(100))
    is_required_candidate: Mapped[bool]


class ImportMappingModel(Base):
    __tablename__ = "import_mappings"
    __table_args__ = (
        UniqueConstraint("source_column_id"),
        UniqueConstraint("import_sheet_id", "canonical_field_code"),
        ForeignKeyConstraint(
            ["import_id", "import_sheet_id"],
            ["import_sheets.import_id", "import_sheets.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["import_sheet_id", "source_column_id"],
            ["import_columns.import_sheet_id", "import_columns.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence"),
        CheckConstraint(
            "mapping_status IN ('EXACT','ALIAS_MATCH','AMBIGUOUS','UNMAPPED','USER_CONFIRMED')",
            name="status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("imports.id", ondelete="RESTRICT"), index=True
    )
    import_sheet_id: Mapped[UUID] = mapped_column(index=True)
    source_column_id: Mapped[UUID] = mapped_column(index=True)
    canonical_field_code: Mapped[str | None] = mapped_column(String(50))
    mapping_status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    confirmed_at: Mapped[datetime | None]


class ImportValidationErrorModel(Base):
    __tablename__ = "import_validation_errors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["import_id", "import_sheet_id"],
            ["import_sheets.import_id", "import_sheets.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("row_number >= 1 AND column_index >= 0", name="locator"),
        CheckConstraint("severity IN ('ERROR','WARNING')", name="severity"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("imports.id", ondelete="RESTRICT"), index=True
    )
    import_sheet_id: Mapped[UUID] = mapped_column(index=True)
    row_number: Mapped[int]
    column_index: Mapped[int]
    error_code: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(String(200))
    canonical_field_code: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime]


class ImportEvidenceModel(Base):
    __tablename__ = "import_evidences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "import_id"], ["imports.company_id", "imports.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
    )
    import_id: Mapped[UUID] = mapped_column(primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    relation_type: Mapped[str] = mapped_column(String(20))


class ImportReceiptModel(Base):
    __tablename__ = "import_receipts"
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("import_id"),
        ForeignKeyConstraint(
            ["company_id", "import_id"], ["imports.company_id", "imports.id"], ondelete="RESTRICT"
        ),
        CheckConstraint(
            "transaction_count = 0 AND counterparty_count = 0 AND evidence_count >= 1",
            name="counts",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    import_id: Mapped[UUID] = mapped_column(index=True)
    source_digest: Mapped[str] = mapped_column(String(64))
    transaction_count: Mapped[int]
    evidence_count: Mapped[int]
    counterparty_count: Mapped[int]
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime]


class ImportConfirmationModel(Base):
    __tablename__ = "import_confirmations"
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "import_id"], ["imports.company_id", "imports.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            ["import_receipts.company_id", "import_receipts.id"],
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    import_id: Mapped[UUID] = mapped_column(index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    receipt_id: Mapped[UUID] = mapped_column(index=True)
    created_at: Mapped[datetime]


class ImportSourceRecordModel(Base):
    __tablename__ = "import_source_records"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "source_type", "target_context", "source_system", "source_id"
        ),
        ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            ["import_receipts.company_id", "import_receipts.id"],
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(30))
    target_context: Mapped[str] = mapped_column(String(30))
    source_system: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str] = mapped_column(String(100))
    content_digest: Mapped[str] = mapped_column(String(64))
    receipt_id: Mapped[UUID] = mapped_column(index=True)
