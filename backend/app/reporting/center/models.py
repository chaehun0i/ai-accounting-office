"""Relational report runs; source and output are immutable references."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class ReportRunModel(UUIDPrimaryKey, Base):
    __tablename__ = "report_generation_runs"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    report_code: Mapped[str] = mapped_column(String(32))
    format: Mapped[str] = mapped_column(String(8))
    period_preset: Mapped[str] = mapped_column(String(16))
    period_mode: Mapped[str] = mapped_column(String(8))
    date_from: Mapped[date | None]
    date_to: Mapped[date | None]
    as_of: Mapped[date | None]
    period_id: Mapped[UUID]
    statement_set_id: Mapped[UUID]
    close_version: Mapped[int]
    taxonomy_version: Mapped[int]
    trial_balance_digest: Mapped[str] = mapped_column(String(64))
    mapping_digest: Mapped[str] = mapped_column(String(64))
    balance_sheet_digest: Mapped[str] = mapped_column(String(64))
    income_statement_digest: Mapped[str] = mapped_column(String(64))
    source_digest: Mapped[str] = mapped_column(String(64))
    template_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(16))
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    requested_at: Mapped[datetime]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(String(48))
    retry_of_run_id: Mapped[UUID | None]
    version: Mapped[int]

    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "requested_by", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "retry_of_run_id"],
            ["report_generation_runs.company_id", "report_generation_runs.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_report_generation_runs_company_requested", "company_id", "requested_at"),
        CheckConstraint(
            "report_code IN ('BALANCE_SHEET','INCOME_STATEMENT','FINANCIAL_METRICS')",
            name="report_code",
        ),
        CheckConstraint("format IN ('PDF','XLSX','CSV')", name="format"),
        CheckConstraint("period_mode IN ('AS_OF','RANGE')", name="period_mode"),
        CheckConstraint(
            "(period_mode = 'AS_OF' AND as_of IS NOT NULL AND date_from IS NULL "
            "AND date_to IS NULL) OR (period_mode = 'RANGE' AND as_of IS NULL "
            "AND date_from IS NOT NULL AND date_to IS NOT NULL "
            "AND date_from <= date_to)",
            name="period_dates",
        ),
        CheckConstraint("status IN ('REQUESTED','GENERATING','COMPLETED','FAILED')", name="status"),
        CheckConstraint(
            "close_version >= 1 AND taxonomy_version >= 1 "
            "AND template_version >= 1 AND version >= 1",
            name="version",
        ),
    )


class ReportArtifactModel(UUIDPrimaryKey, Base):
    __tablename__ = "report_generation_artifacts"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    run_id: Mapped[UUID]
    storage_object_id: Mapped[UUID]
    file_name: Mapped[str] = mapped_column(String(180))
    file_sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime | None]

    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "run_id"),
        ForeignKeyConstraint(
            ["company_id", "run_id"],
            ["report_generation_runs.company_id", "report_generation_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "storage_object_id", "file_sha256"],
            ["storage_objects.company_id", "storage_objects.id", "storage_objects.sha256"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 2000000", name="size"),
    )
