"""형식이 고정된 초안 값과 관계형 이력·접수증을 저장합니다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.types import MoneyNumeric


class OnboardingSessionModel(Base):
    __tablename__ = "onboarding_sessions"
    __table_args__ = (
        UniqueConstraint("company_id"),
        UniqueConstraint("company_id", "id"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "status IN ('NOT_STARTED','IN_PROGRESS','REVIEW_REQUIRED','READY_TO_COMPLETE','COMPLETED')",
            name="status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(24))
    current_step: Mapped[str] = mapped_column(String(40))
    started_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(default=1)


class FieldDefinitionModel(Base):
    __tablename__ = "onboarding_field_definitions"
    __table_args__ = (
        UniqueConstraint("field_code"),
        UniqueConstraint("id", "section_code"),
        CheckConstraint("data_type IN ('TEXT','NUMERIC','DATE','BOOLEAN')", name="data_type"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    field_code: Mapped[str] = mapped_column(String(100))
    section_code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(100))
    data_type: Mapped[str] = mapped_column(String(12))
    input_mode: Mapped[str] = mapped_column(String(24))
    required_rule_code: Mapped[str] = mapped_column(String(32))
    enum_source_code: Mapped[str | None] = mapped_column(String(40))
    derived_handler_key: Mapped[str | None] = mapped_column(String(40))
    display_order: Mapped[int]
    active: Mapped[bool]


class ScopedSession:
    company_id: Mapped[UUID] = mapped_column(index=True)
    session_id: Mapped[UUID] = mapped_column(index=True)


def scope_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["company_id", "session_id"],
        ["onboarding_sessions.company_id", "onboarding_sessions.id"],
        ondelete="RESTRICT",
    )


class SectionModel(ScopedSession, Base):
    __tablename__ = "onboarding_sections"
    __table_args__ = (scope_fk(), UniqueConstraint("session_id", "section_code"))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    section_code: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16))
    display_order: Mapped[int]
    required: Mapped[bool]


class RowItemModel(ScopedSession, Base):
    __tablename__ = "onboarding_row_items"
    __table_args__ = (scope_fk(), UniqueConstraint("session_id", "section_code", "row_key"))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    section_code: Mapped[str] = mapped_column(String(40))
    row_key: Mapped[str] = mapped_column(String(260))


class TypedValue:
    value_text: Mapped[str | None] = mapped_column(String(500))
    value_numeric: Mapped[Decimal | None] = mapped_column(MoneyNumeric())
    value_date: Mapped[date | None]
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    source_type: Mapped[str] = mapped_column(String(20))
    source_import_id: Mapped[UUID | None] = mapped_column(index=True)


def typed_check() -> CheckConstraint:
    return CheckConstraint(
        "num_nonnulls(value_text,value_numeric,value_date,value_boolean) = 1",
        name="one_typed_value",
    )


def import_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["company_id", "source_import_id"],
        ["imports.company_id", "imports.id"],
        ondelete="RESTRICT",
    )


class ValueModel(ScopedSession, TypedValue, Base):
    __tablename__ = "onboarding_values"
    __table_args__ = (
        scope_fk(),
        import_fk(),
        typed_check(),
        ForeignKeyConstraint(
            ["field_definition_id", "section_code"],
            ["onboarding_field_definitions.id", "onboarding_field_definitions.section_code"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["session_id", "section_code", "row_key"],
            [
                "onboarding_row_items.session_id",
                "onboarding_row_items.section_code",
                "onboarding_row_items.row_key",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("session_id", "field_definition_id", "row_key"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "source_type IN ('MANUAL','EXCEL_IMPORT','SYSTEM_DEFAULT','DERIVED')",
            name="source_type",
        ),
        CheckConstraint("status IN ('DRAFT','VALID','INVALID','STALE')", name="status"),
        CheckConstraint(
            "source_type != 'EXCEL_IMPORT' OR source_import_id IS NOT NULL", name="source_reference"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    field_definition_id: Mapped[UUID] = mapped_column(index=True)
    section_code: Mapped[str] = mapped_column(String(40))
    row_key: Mapped[str] = mapped_column(String(260))
    status: Mapped[str] = mapped_column(String(16))
    version: Mapped[int]
    updated_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    updated_at: Mapped[datetime]


class ValueHistoryModel(ScopedSession, TypedValue, Base):
    __tablename__ = "onboarding_value_history"
    __table_args__ = (
        scope_fk(),
        import_fk(),
        typed_check(),
        UniqueConstraint("value_id", "version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    value_id: Mapped[UUID] = mapped_column(
        ForeignKey("onboarding_values.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[int]
    updated_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    updated_at: Mapped[datetime]


class ValidationResultModel(ScopedSession, Base):
    __tablename__ = "onboarding_validation_results"
    __table_args__ = (scope_fk(),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    field_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("onboarding_field_definitions.id", ondelete="RESTRICT"), index=True
    )
    row_key: Mapped[str] = mapped_column(String(260))
    validation_code: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime]


class OnboardingImportModel(ScopedSession, Base):
    __tablename__ = "onboarding_imports"
    __table_args__ = (
        scope_fk(),
        ForeignKeyConstraint(
            ["company_id", "import_id"], ["imports.company_id", "imports.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("import_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_id: Mapped[UUID] = mapped_column(index=True)
    template_code: Mapped[str] = mapped_column(String(40))
    template_version: Mapped[str] = mapped_column(String(16))
    schema_version: Mapped[str] = mapped_column(String(16))
    generated_at: Mapped[datetime]
    locale: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24))


class ApplyReceiptModel(ScopedSession, Base):
    __tablename__ = "onboarding_apply_receipts"
    __table_args__ = (
        scope_fk(),
        ForeignKeyConstraint(
            ["company_id", "import_id"], ["imports.company_id", "imports.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("company_id", "idempotency_key"),
        UniqueConstraint("import_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_id: Mapped[UUID] = mapped_column(index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    source_digest: Mapped[str] = mapped_column(String(64))
    new_count: Mapped[int]
    changed_count: Mapped[int]
    unchanged_count: Mapped[int]
    conflict_count: Mapped[int]
    error_count: Mapped[int]
    created_at: Mapped[datetime]


class PromotionReceiptModel(ScopedSession, Base):
    __tablename__ = "onboarding_promotion_receipts"
    __table_args__ = (
        scope_fk(),
        UniqueConstraint("session_id"),
        UniqueConstraint("company_id", "idempotency_key"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    account_count: Mapped[int]
    counterparty_count: Mapped[int]
    created_at: Mapped[datetime]
