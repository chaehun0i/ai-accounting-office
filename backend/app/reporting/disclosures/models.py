"""Relational disclosure registry and immutable generated facts."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class DisclosureTemplateModel(UUIDPrimaryKey, Base):
    __tablename__ = "disclosure_templates"
    framework_code: Mapped[str] = mapped_column(String(32))
    template_code: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(160))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(12))
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    __table_args__ = (
        UniqueConstraint("framework_code", "template_code", "version"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="dates"),
    )


class DisclosureSectionModel(UUIDPrimaryKey, Base):
    __tablename__ = "disclosure_sections"
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("disclosure_templates.id", ondelete="RESTRICT")
    )
    section_code: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(160))
    display_order: Mapped[int]
    requirement_rule_key: Mapped[str] = mapped_column(String(48))
    __table_args__ = (
        UniqueConstraint("template_id", "id"),
        UniqueConstraint("template_id", "section_code"),
        CheckConstraint("display_order > 0", name="display_order"),
    )


class DisclosureFieldModel(UUIDPrimaryKey, Base):
    __tablename__ = "disclosure_fields"
    template_id: Mapped[UUID]
    section_id: Mapped[UUID]
    field_code: Mapped[str] = mapped_column(String(48))
    label: Mapped[str] = mapped_column(String(160))
    data_type: Mapped[str] = mapped_column(String(12))
    required: Mapped[bool]
    source_fact_type: Mapped[str] = mapped_column(String(32))
    aggregation_handler_key: Mapped[str] = mapped_column(String(48))
    __table_args__ = (
        UniqueConstraint("template_id", "id"),
        UniqueConstraint("section_id", "id"),
        UniqueConstraint("section_id", "field_code"),
        ForeignKeyConstraint(
            ["template_id", "section_id"],
            ["disclosure_sections.template_id", "disclosure_sections.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("data_type IN ('TEXT','DECIMAL','DATE','BOOLEAN')", name="data_type"),
        CheckConstraint(
            "source_fact_type IN ('STATEMENT_LINE','GL_ACCOUNT','CASH_FLOW_LINE','EQUITY_LINE')",
            name="source_fact",
        ),
    )


class DisclosureInstanceModel(UUIDPrimaryKey, Base):
    __tablename__ = "disclosure_instances"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    statement_set_id: Mapped[UUID]
    period_id: Mapped[UUID]
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("disclosure_templates.id", ondelete="RESTRICT")
    )
    template_version: Mapped[int]
    revision: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))
    balance_sheet_digest: Mapped[str] = mapped_column(String(64))
    income_statement_digest: Mapped[str] = mapped_column(String(64))
    cash_flow_digest: Mapped[str] = mapped_column(String(64))
    equity_digest: Mapped[str] = mapped_column(String(64))
    source_digest: Mapped[str] = mapped_column(String(64))
    reconciliation_status: Mapped[str] = mapped_column(String(16))
    reconciliation_digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None]
    version: Mapped[int]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint(
            "company_id",
            "period_id",
            "source_digest",
            "revision",
            name="uq_disclosure_instances_source_revision",
        ),
        Index("ix_disclosure_instances_company_period", "company_id", "period_id"),
        ForeignKeyConstraint(
            ["company_id", "statement_set_id"],
            ["financial_statement_sets.company_id", "financial_statement_sets.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("template_version > 0 AND revision > 0 AND version > 0", name="version"),
        CheckConstraint(
            "status IN ('DRAFT','BLOCKED','REVIEW_REQUESTED','APPROVED','REJECTED')",
            name="status",
        ),
        CheckConstraint("reconciliation_status = 'RECONCILED'", name="reconciliation_status"),
        CheckConstraint(
            "(status = 'APPROVED' AND approved_by IS NOT NULL AND approved_at IS NOT NULL) OR "
            "(status <> 'APPROVED' AND approved_by IS NULL AND approved_at IS NULL)",
            name="approval_fields",
        ),
    )


class DisclosureValueModel(UUIDPrimaryKey, Base):
    __tablename__ = "disclosure_values"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    instance_id: Mapped[UUID]
    section_id: Mapped[UUID]
    field_id: Mapped[UUID]
    source_type: Mapped[str] = mapped_column(String(24))
    source_id: Mapped[UUID]
    statement_line_id: Mapped[UUID | None]
    cash_flow_line_id: Mapped[UUID | None]
    equity_line_id: Mapped[UUID | None]
    account_id: Mapped[UUID | None]
    source_code: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(160))
    text_value: Mapped[str | None] = mapped_column(Text)
    decimal_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    date_value: Mapped[date | None]
    boolean_value: Mapped[bool | None]
    validation_status: Mapped[str] = mapped_column(String(16))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint(
            "instance_id",
            "source_type",
            "source_id",
            "statement_line_id",
            name="uq_disclosure_values_instance_source",
        ),
        Index("ix_disclosure_values_company_instance", "company_id", "instance_id"),
        ForeignKeyConstraint(
            ["company_id", "instance_id"],
            ["disclosure_instances.company_id", "disclosure_instances.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "statement_line_id"],
            ["financial_statement_lines.company_id", "financial_statement_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "cash_flow_line_id"],
            ["cash_flow_lines.company_id", "cash_flow_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "equity_line_id"],
            ["equity_statement_lines.company_id", "equity_statement_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["section_id", "field_id"],
            ["disclosure_fields.section_id", "disclosure_fields.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "source_type IN ('BALANCE_SHEET','INCOME_STATEMENT','CASH_FLOW','CHANGES_IN_EQUITY')",
            name="source_type",
        ),
        CheckConstraint(
            "(source_type IN ('BALANCE_SHEET','INCOME_STATEMENT') "
            "AND statement_line_id = source_id AND account_id IS NULL "
            "AND cash_flow_line_id IS NULL AND equity_line_id IS NULL) OR "
            "(source_type IN ('BALANCE_SHEET','INCOME_STATEMENT') "
            "AND statement_line_id IS NOT NULL AND account_id = source_id "
            "AND cash_flow_line_id IS NULL AND equity_line_id IS NULL) OR "
            "(source_type = 'CASH_FLOW' AND statement_line_id IS NULL "
            "AND account_id IS NULL AND cash_flow_line_id = source_id "
            "AND equity_line_id IS NULL) OR "
            "(source_type = 'CHANGES_IN_EQUITY' AND statement_line_id IS NULL "
            "AND account_id IS NULL AND cash_flow_line_id IS NULL AND equity_line_id = source_id)",
            name="source_reference",
        ),
        CheckConstraint("validation_status = 'VALIDATED'", name="validation_status"),
        CheckConstraint(
            "num_nonnulls(text_value, decimal_value, date_value, boolean_value) = 1",
            name="one_typed_value",
        ),
    )


class DisclosureAuditModel(UUIDPrimaryKey, Base):
    __tablename__ = "disclosure_audit_events"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    instance_id: Mapped[UUID]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    expected_version: Mapped[int]
    created_at: Mapped[datetime]
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "instance_id"],
            ["disclosure_instances.company_id", "disclosure_instances.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("expected_version > 0", name="version"),
        Index("ix_disclosure_audit_company_instance", "company_id", "instance_id"),
    )


class DisclosureNarrativeModel(UUIDPrimaryKey, Base):
    __tablename__ = "disclosure_narratives"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    instance_id: Mapped[UUID]
    section_id: Mapped[UUID]
    text_value: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    source_digest: Mapped[str] = mapped_column(String(64))
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime]
    version: Mapped[int]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("instance_id", "section_id"),
        ForeignKeyConstraint(
            ["company_id", "instance_id"],
            ["disclosure_instances.company_id", "disclosure_instances.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["section_id"], ["disclosure_sections.id"], ondelete="RESTRICT"),
        CheckConstraint("status IN ('DRAFT','APPROVED') AND version > 0", name="status"),
    )


class DisclosureCommandModel(UUIDPrimaryKey, Base):
    __tablename__ = "disclosure_commands"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    instance_id: Mapped[UUID]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "actor_id",
            "idempotency_key",
            name="uq_disclosure_commands_company_actor_key",
        ),
        ForeignKeyConstraint(
            ["company_id", "instance_id"],
            ["disclosure_instances.company_id", "disclosure_instances.id"],
            ondelete="RESTRICT",
        ),
    )
