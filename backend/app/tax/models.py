from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class TaxProfileModel(UUIDPrimaryKey, Base):
    __tablename__ = "tax_profiles"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    version: Mapped[int]
    taxpayer_type: Mapped[str] = mapped_column(String(24))
    tax_regime: Mapped[str] = mapped_column(String(20))
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    source: Mapped[str] = mapped_column(String(200))
    has_employees: Mapped[bool]
    pays_business_income: Mapped[bool]
    pays_other_income: Mapped[bool]
    uses_daily_workers: Mapped[bool]
    has_exports: Mapped[bool]
    has_exempt_sales: Mapped[bool]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "version"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="dates"),
        CheckConstraint("taxpayer_type IN ('INDIVIDUAL_BUSINESS','CORPORATION')", name="taxpayer"),
        CheckConstraint(
            "tax_regime IN ('VAT_GENERAL','VAT_SIMPLIFIED','VAT_EXEMPT')", name="regime"
        ),
        CheckConstraint(
            "taxpayer_type <> 'CORPORATION' OR tax_regime <> 'VAT_SIMPLIFIED'", name="combination"
        ),
    )


class TaxPeriodModel(UUIDPrimaryKey, Base):
    __tablename__ = "tax_periods"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    tax_type: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[date]
    period_end: Mapped[date]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "tax_type", "period_start", "period_end"),
        CheckConstraint("tax_type IN ('VAT','WITHHOLDING')", name="type"),
        CheckConstraint("period_start <= period_end", name="dates"),
    )


class TaxFact:
    revision: Mapped[int]
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    period_id: Mapped[UUID]
    transaction_id: Mapped[UUID]
    transaction_version: Mapped[int]
    source_digest: Mapped[str] = mapped_column(String(64))
    evidence_id: Mapped[UUID | None]
    rule_reference: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]


def fact_constraints() -> tuple[UniqueConstraint | ForeignKeyConstraint | CheckConstraint, ...]:
    return (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "transaction_id", "revision"),
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["tax_periods.company_id", "tax_periods.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "transaction_id"],
            ["transactions.company_id", "transactions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("transaction_version >= 1", name="transaction_version"),
        CheckConstraint("revision >= 1", name="revision"),
    )


class VatModel(UUIDPrimaryKey, TaxFact, Base):
    __tablename__ = "vat_treatments"
    direction: Mapped[str] = mapped_column(String(12))
    tax_category: Mapped[str] = mapped_column(String(16))
    supply_amount: Mapped[Decimal]
    tax_amount: Mapped[Decimal]
    deductible_status: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str] = mapped_column(String(80))
    __table_args__ = (
        *fact_constraints(),
        CheckConstraint("direction IN ('INFLOW','OUTFLOW')", name="direction"),
        CheckConstraint(
            "tax_category IN ('TAXABLE','ZERO_RATED','EXEMPT','OUT_OF_SCOPE')", name="category"
        ),
        CheckConstraint("supply_amount >= 0 AND tax_amount >= 0", name="amounts"),
        CheckConstraint("tax_category = 'TAXABLE' OR tax_amount = 0", name="category_tax"),
        CheckConstraint(
            "deductible_status IN ('DEDUCTIBLE','NON_DEDUCTIBLE','REVIEW_REQUIRED','NOT_APPLICABLE')",
            name="deduction",
        ),
        CheckConstraint(
            "direction <> 'INFLOW' OR deductible_status = 'NOT_APPLICABLE'", name="sales_deduction"
        ),
        CheckConstraint(
            "deductible_status <> 'DEDUCTIBLE' OR tax_category = 'TAXABLE'",
            name="taxable_deduction",
        ),
    )


class WithholdingModel(UUIDPrimaryKey, TaxFact, Base):
    __tablename__ = "withholding_items"
    payee_id: Mapped[UUID]
    payment_date: Mapped[date]
    income_type: Mapped[str] = mapped_column(String(24))
    gross_amount: Mapped[Decimal]
    taxable_base: Mapped[Decimal]
    withholding_tax: Mapped[Decimal]
    local_tax: Mapped[Decimal]
    net_amount: Mapped[Decimal]
    __table_args__ = (
        *fact_constraints(),
        ForeignKeyConstraint(
            ["company_id", "payee_id"],
            ["counterparties.company_id", "counterparties.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "income_type IN ('EMPLOYMENT_INCOME','BUSINESS_INCOME','OTHER_INCOME','DAILY_WORKER')",
            name="income_type",
        ),
        CheckConstraint(
            "gross_amount >= 0 AND taxable_base >= 0 AND taxable_base <= gross_amount AND withholding_tax >= 0 AND local_tax >= 0 AND net_amount >= 0",
            name="amounts",
        ),
        CheckConstraint(
            "net_amount + withholding_tax + local_tax = gross_amount", name="reconciliation"
        ),
    )


class TaxCommandModel(UUIDPrimaryKey, Base):
    __tablename__ = "tax_commands"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    command_code: Mapped[str] = mapped_column(String(24))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    profile_id: Mapped[UUID | None]
    period_id: Mapped[UUID | None]
    vat_id: Mapped[UUID | None]
    withholding_id: Mapped[UUID | None]
    occurred_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "command_code", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "profile_id"],
            ["tax_profiles.company_id", "tax_profiles.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["tax_periods.company_id", "tax_periods.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "vat_id"],
            ["vat_treatments.company_id", "vat_treatments.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "withholding_id"],
            ["withholding_items.company_id", "withholding_items.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "num_nonnulls(profile_id, period_id, vat_id, withholding_id) = 1", name="one_result"
        ),
    )
