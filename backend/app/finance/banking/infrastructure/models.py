"""계좌 원번호 없이 별칭과 명시적 장부 계정만 저장합니다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


def scoped_fk(column: str, target: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["company_id", column], [target + ".company_id", target + ".id"], ondelete="RESTRICT"
    )


class BankAccountModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "bank_accounts"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    institution_code: Mapped[str] = mapped_column(String(30))
    alias: Mapped[str] = mapped_column(String(80))
    control_account_id: Mapped[UUID] = mapped_column(index=True)
    currency_code: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "alias"),
        scoped_fk("control_account_id", "chart_of_accounts"),
        CheckConstraint("currency_code = 'KRW'", name="currency"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("version >= 1", name="version"),
    )


class CardAccountModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "card_accounts"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    institution_code: Mapped[str] = mapped_column(String(30))
    alias: Mapped[str] = mapped_column(String(80))
    control_account_id: Mapped[UUID] = mapped_column(index=True)
    currency_code: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16))
    usage_type: Mapped[str] = mapped_column(String(16), server_default="CORPORATE")
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "alias"),
        scoped_fk("control_account_id", "chart_of_accounts"),
        CheckConstraint("usage_type IN ('CORPORATE','MERCHANT')", name="usage"),
        CheckConstraint("currency_code = 'KRW'", name="currency"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("version >= 1", name="version"),
    )


class BankStatementModel(UUIDPrimaryKey, Versioned, Base):
    __tablename__ = "bank_statements"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    bank_account_id: Mapped[UUID] = mapped_column(index=True)
    statement_start: Mapped[date]
    statement_end: Mapped[date]
    opening_balance: Mapped[Decimal]
    closing_balance: Mapped[Decimal]
    currency_code: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24))
    source_import_id: Mapped[UUID] = mapped_column(index=True)
    source_receipt_id: Mapped[UUID] = mapped_column(index=True)
    source_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "bank_account_id", "statement_start", "statement_end"),
        UniqueConstraint("company_id", "source_import_id"),
        scoped_fk("bank_account_id", "bank_accounts"),
        scoped_fk("source_import_id", "imports"),
        ForeignKeyConstraint(
            ["company_id", "source_import_id", "source_receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("statement_start <= statement_end", name="dates"),
        CheckConstraint("currency_code = 'KRW'", name="currency"),
        CheckConstraint(
            "abs(opening_balance) < 1000000000000000 AND abs(closing_balance) < 1000000000000000",
            name="balances",
        ),
        CheckConstraint(
            "status IN ('IMPORTED','RECONCILING','REVIEW_REQUIRED','RECONCILED','CLOSED')",
            name="status",
        ),
        CheckConstraint("version >= 1", name="version"),
    )


class BankTransactionModel(UUIDPrimaryKey, Base):
    __tablename__ = "bank_transactions"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    account_id: Mapped[UUID] = mapped_column(index=True)
    source_system: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str] = mapped_column(String(100))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(index=True)
    direction: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal]
    counterparty_text: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500))
    reference: Mapped[str] = mapped_column(String(100))
    source_status: Mapped[str] = mapped_column(String(16))
    source_import_id: Mapped[UUID] = mapped_column(index=True)
    source_receipt_id: Mapped[UUID] = mapped_column(index=True)
    sheet_index: Mapped[int]
    row_number: Mapped[int]
    version: Mapped[int]
    balance_after: Mapped[Decimal | None]
    statement_id: Mapped[UUID] = mapped_column(index=True)
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "account_id", "source_system", "source_id"),
        scoped_fk("account_id", "bank_accounts"),
        scoped_fk("source_import_id", "imports"),
        ForeignKeyConstraint(
            ["company_id", "source_import_id", "source_receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            ondelete="RESTRICT",
        ),
        scoped_fk("statement_id", "bank_statements"),
        CheckConstraint("amount > 0 AND amount < 1000000000000000", name="amount"),
        CheckConstraint("direction IN ('IN','OUT')", name="direction"),
        CheckConstraint(
            "source_status IN ('AUTHORIZED','CAPTURED','CANCELLED','REFUNDED','REVERSED')",
            name="source_status",
        ),
        CheckConstraint("version >= 1 AND sheet_index >= 0 AND row_number >= 2", name="locator"),
    )


class CardTransactionModel(UUIDPrimaryKey, Base):
    __tablename__ = "card_transactions"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    account_id: Mapped[UUID] = mapped_column(index=True)
    source_system: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str] = mapped_column(String(100))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(index=True)
    direction: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal]
    counterparty_text: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500))
    reference: Mapped[str] = mapped_column(String(100))
    source_status: Mapped[str] = mapped_column(String(16))
    source_import_id: Mapped[UUID] = mapped_column(index=True)
    source_receipt_id: Mapped[UUID] = mapped_column(index=True)
    sheet_index: Mapped[int]
    row_number: Mapped[int]
    version: Mapped[int]

    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "account_id", "source_system", "source_id"),
        scoped_fk("account_id", "card_accounts"),
        scoped_fk("source_import_id", "imports"),
        ForeignKeyConstraint(
            ["company_id", "source_import_id", "source_receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0 AND amount < 1000000000000000", name="amount"),
        CheckConstraint("direction IN ('IN','OUT')", name="direction"),
        CheckConstraint(
            "source_status IN ('AUTHORIZED','CAPTURED','CANCELLED','REFUNDED','REVERSED')",
            name="source_status",
        ),
        CheckConstraint("version >= 1 AND sheet_index >= 0 AND row_number >= 2", name="locator"),
    )


class ReconciliationPolicyModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "reconciliation_policies"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), unique=True
    )
    allowed_days: Mapped[int]
    amount_tolerance: Mapped[Decimal]
    auto_threshold: Mapped[int]
    review_threshold: Mapped[int]
    materiality: Mapped[Decimal]
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    __table_args__ = (
        CheckConstraint("allowed_days BETWEEN 0 AND 90 AND version >= 1", name="days_version"),
        CheckConstraint(
            "review_threshold BETWEEN 0 AND 100 AND auto_threshold BETWEEN "
            "review_threshold AND 100",
            name="thresholds",
        ),
        CheckConstraint(
            "amount_tolerance >= 0 AND amount_tolerance < 1000000000000000 AND "
            "materiality >= 0 AND materiality < 1000000000000000",
            name="amounts",
        ),
    )


class ReconciliationItemModel(UUIDPrimaryKey, Base):
    __tablename__ = "reconciliation_items"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    statement_id: Mapped[UUID] = mapped_column(index=True)
    reason_code: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal]
    status: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(server_default="1")
    resolution_note: Mapped[str | None] = mapped_column(String(500))
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    resolved_at: Mapped[datetime | None]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    __table_args__ = (
        scoped_fk("statement_id", "bank_statements"),
        CheckConstraint(
            "reason_code IN "
            "('TIMING_ITEM','MISSING_TRANSACTION','DUPLICATE_SOURCE','WRONG_ACCOUNT','MANUAL_ADJUSTMENT_CANDIDATE','UNKNOWN')",
            name="reason",
        ),
        CheckConstraint("status IN ('OPEN','RESOLVED')", name="status"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "(status = 'OPEN' AND resolution_note IS NULL AND resolved_by IS NULL "
            "AND resolved_at IS NULL) OR (status = 'RESOLVED' AND resolution_note IS NOT NULL "
            "AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)",
            name="resolution",
        ),
        CheckConstraint("abs(amount) < 1000000000000000", name="amount"),
    )


class ReconciliationEventModel(UUIDPrimaryKey, Base):
    __tablename__ = "reconciliation_events"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    command_code: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    statement_id: Mapped[UUID | None] = mapped_column(index=True)
    reconciliation_id: Mapped[UUID | None] = mapped_column(index=True)
    card_account_id: Mapped[UUID | None] = mapped_column(index=True)
    result_version: Mapped[int]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "command_code", "idempotency_key"),
        scoped_fk("statement_id", "bank_statements"),
        scoped_fk("reconciliation_id", "reconciliation_matches"),
        scoped_fk("card_account_id", "card_accounts"),
        CheckConstraint(
            "num_nonnulls(statement_id,reconciliation_id,card_account_id) = 1", name="result"
        ),
        CheckConstraint("result_version >= 1", name="version"),
    )
