"""회사와 분석축 일치를 복합 외래키로 보장합니다."""

from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class DimensionModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "accounting_dimensions"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    dimension_code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    dimension_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    required_policy: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "id", "dimension_type"),
        UniqueConstraint("company_id", "dimension_code"),
        CheckConstraint(
            "dimension_type IN ('BUSINESS_UNIT','DEPARTMENT','PROJECT','COST_CENTER')", name="type"
        ),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("required_policy IN ('OPTIONAL','REQUIRED')", name="required_policy"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("dimension_code ~ '^[A-Z0-9][A-Z0-9_-]{0,39}$'", name="code"),
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 200", name="name"),
    )


class DimensionValueModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "accounting_dimension_values"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    dimension_id: Mapped[UUID] = mapped_column(index=True)
    value_code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    parent_value_id: Mapped[UUID | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20))
    effective_from: Mapped[date | None]
    effective_to: Mapped[date | None]
    __table_args__ = (
        UniqueConstraint("company_id", "dimension_id", "id"),
        UniqueConstraint("dimension_id", "value_code"),
        ForeignKeyConstraint(
            ["company_id", "dimension_id"],
            ["accounting_dimensions.company_id", "accounting_dimensions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "dimension_id", "parent_value_id"],
            [
                "accounting_dimension_values.company_id",
                "accounting_dimension_values.dimension_id",
                "accounting_dimension_values.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "effective_from IS NULL OR effective_to IS NULL OR effective_from <= effective_to",
            name="effective_dates",
        ),
        CheckConstraint("parent_value_id IS NULL OR parent_value_id <> id", name="parent"),
        CheckConstraint("value_code ~ '^[A-Z0-9][A-Z0-9_-]{0,39}$'", name="code"),
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 200", name="name"),
    )


class JournalLineDimensionModel(UUIDPrimaryKey, Base):
    __tablename__ = "journal_line_dimensions"
    company_id: Mapped[UUID] = mapped_column(index=True)
    journal_line_id: Mapped[UUID] = mapped_column(index=True)
    dimension_id: Mapped[UUID]
    dimension_type: Mapped[str] = mapped_column(String(30))
    dimension_value_id: Mapped[UUID] = mapped_column(index=True)
    __table_args__ = (
        UniqueConstraint("journal_line_id", "dimension_id"),
        UniqueConstraint("journal_line_id", "dimension_type"),
        ForeignKeyConstraint(
            ["company_id", "journal_line_id"],
            ["journal_lines.company_id", "journal_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "dimension_id", "dimension_type"],
            [
                "accounting_dimensions.company_id",
                "accounting_dimensions.id",
                "accounting_dimensions.dimension_type",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "dimension_id", "dimension_value_id"],
            [
                "accounting_dimension_values.company_id",
                "accounting_dimension_values.dimension_id",
                "accounting_dimension_values.id",
            ],
            ondelete="RESTRICT",
        ),
    )
