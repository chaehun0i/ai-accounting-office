"""문서 종류별 정본과 회사 복합 외래키를 정의합니다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class DocumentColumns(UUIDPrimaryKey, Timestamped, Versioned):
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    document_no: Mapped[str] = mapped_column(String(100))
    counterparty_id: Mapped[UUID] = mapped_column(index=True)
    issue_date: Mapped[date] = mapped_column(index=True)
    accounting_date: Mapped[date]
    due_date: Mapped[date]
    currency_code: Mapped[str] = mapped_column(String(3))
    supply_amount: Mapped[Decimal]
    tax_amount: Mapped[Decimal]
    total_amount: Mapped[Decimal]
    status: Mapped[str] = mapped_column(String(30))
    source_system: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str] = mapped_column(String(100))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    source_import_id: Mapped[UUID | None] = mapped_column(index=True)
    evidence_id: Mapped[UUID | None] = mapped_column(index=True)
    transaction_id: Mapped[UUID | None] = mapped_column(index=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    approved_at: Mapped[datetime | None]

    @declared_attr.directive
    def __table_args__(cls) -> tuple[object, ...]:
        return (
            UniqueConstraint("company_id", "id"),
            UniqueConstraint("company_id", "document_no"),
            UniqueConstraint("company_id", "source_system", "source_id"),
            UniqueConstraint("company_id", "transaction_id"),
            ForeignKeyConstraint(
                ["company_id", "counterparty_id"],
                ["counterparties.company_id", "counterparties.id"],
                ondelete="RESTRICT",
            ),
            ForeignKeyConstraint(
                ["company_id", "source_import_id"],
                ["imports.company_id", "imports.id"],
                ondelete="RESTRICT",
            ),
            ForeignKeyConstraint(
                ["company_id", "evidence_id"],
                ["evidences.company_id", "evidences.id"],
                ondelete="RESTRICT",
            ),
            ForeignKeyConstraint(
                ["company_id", "transaction_id"],
                ["transactions.company_id", "transactions.id"],
                ondelete="RESTRICT",
            ),
            CheckConstraint("currency_code='KRW'", name="currency"),
            CheckConstraint("version >= 1", name="version"),
            CheckConstraint("due_date >= issue_date", name="dates"),
            CheckConstraint(
                "supply_amount >= 0 AND tax_amount >= 0 AND total_amount > 0 "
                "AND total_amount = supply_amount + tax_amount "
                "AND total_amount < 1000000000000000",
                name="amount",
            ),
            CheckConstraint(
                "status IN ('DRAFT','REVIEW_REQUIRED','APPROVED','APPLIED')", name="status"
            ),
            CheckConstraint(
                "(status IN ('DRAFT','REVIEW_REQUIRED') AND transaction_id IS NULL "
                "AND approved_by IS NULL AND approved_at IS NULL) OR "
                "(status IN ('APPROVED','APPLIED') AND transaction_id IS NOT NULL "
                "AND approved_by IS NOT NULL AND approved_at IS NOT NULL "
                "AND approved_by <> created_by)",
                name="approval",
            ),
        )


class SalesInvoiceModel(DocumentColumns, Base):
    __tablename__ = "sales_invoices"


class PurchaseInvoiceModel(DocumentColumns, Base):
    __tablename__ = "purchase_invoices"


class DocumentNoteModel(DocumentColumns, Base):
    __tablename__ = "document_notes"
    note_type: Mapped[str] = mapped_column(String(20))
    sales_invoice_id: Mapped[UUID | None] = mapped_column(index=True)
    purchase_invoice_id: Mapped[UUID | None] = mapped_column(index=True)
    reason_code: Mapped[str] = mapped_column(String(100))
    original_version: Mapped[int]

    @declared_attr.directive
    def __table_args__(cls) -> tuple[object, ...]:
        return (
            *super().__table_args__,
            ForeignKeyConstraint(
                ["company_id", "sales_invoice_id"],
                ["sales_invoices.company_id", "sales_invoices.id"],
                ondelete="RESTRICT",
            ),
            ForeignKeyConstraint(
                ["company_id", "purchase_invoice_id"],
                ["purchase_invoices.company_id", "purchase_invoices.id"],
                ondelete="RESTRICT",
            ),
            CheckConstraint("note_type IN ('CREDIT_NOTE','DEBIT_NOTE')", name="note_type"),
            CheckConstraint(
                "num_nonnulls(sales_invoice_id,purchase_invoice_id)=1", name="original"
            ),
            CheckConstraint("original_version >= 1", name="original_version"),
        )


class LineColumns(UUIDPrimaryKey):
    company_id: Mapped[UUID] = mapped_column(index=True)
    invoice_id: Mapped[UUID] = mapped_column(index=True)
    line_no: Mapped[int]
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal | None]
    unit_price: Mapped[Decimal | None]
    supply_amount: Mapped[Decimal]
    tax_amount: Mapped[Decimal]


def line_constraints(parent: str) -> tuple[object, ...]:
    return (
        UniqueConstraint("invoice_id", "line_no"),
        ForeignKeyConstraint(
            ["company_id", "invoice_id"],
            [f"{parent}.company_id", f"{parent}.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("line_no >= 1", name="line_no"),
        CheckConstraint(
            "supply_amount >= 0 AND tax_amount >= 0 AND supply_amount + tax_amount > 0 "
            "AND supply_amount + tax_amount < 1000000000000000",
            name="amount",
        ),
        CheckConstraint(
            "(quantity IS NULL AND unit_price IS NULL) OR "
            "(quantity IS NOT NULL AND unit_price IS NOT NULL AND "
            "quantity > 0 AND unit_price >= 0 AND quantity * unit_price = supply_amount)",
            name="quantity",
        ),
    )


class SalesInvoiceLineModel(LineColumns, Base):
    __tablename__ = "sales_invoice_lines"
    __table_args__ = line_constraints("sales_invoices")


class PurchaseInvoiceLineModel(LineColumns, Base):
    __tablename__ = "purchase_invoice_lines"
    __table_args__ = line_constraints("purchase_invoices")


class DocumentNoteLineModel(LineColumns, Base):
    __tablename__ = "document_note_lines"
    __table_args__ = line_constraints("document_notes")


class DocumentEventModel(UUIDPrimaryKey, Base):
    __tablename__ = "business_document_events"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    sales_invoice_id: Mapped[UUID | None] = mapped_column(index=True)
    purchase_invoice_id: Mapped[UUID | None] = mapped_column(index=True)
    document_note_id: Mapped[UUID | None] = mapped_column(index=True)
    command_code: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    before_status: Mapped[str] = mapped_column(String(30))
    after_status: Mapped[str] = mapped_column(String(30))
    result_version: Mapped[int]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "command_code", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "sales_invoice_id"],
            ["sales_invoices.company_id", "sales_invoices.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "purchase_invoice_id"],
            ["purchase_invoices.company_id", "purchase_invoices.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "document_note_id"],
            ["document_notes.company_id", "document_notes.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "num_nonnulls(sales_invoice_id,purchase_invoice_id,document_note_id)=1", name="resource"
        ),
        CheckConstraint("result_version >= 1", name="version"),
    )


class ObligationAdjustmentModel(UUIDPrimaryKey, Base):
    __tablename__ = "obligation_adjustments"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    document_note_id: Mapped[UUID] = mapped_column(index=True)
    receivable_id: Mapped[UUID | None] = mapped_column(index=True)
    payable_id: Mapped[UUID | None] = mapped_column(index=True)
    adjustment_type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal]
    effective_date: Mapped[date]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "document_note_id"),
        ForeignKeyConstraint(
            ["company_id", "document_note_id"],
            ["document_notes.company_id", "document_notes.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "receivable_id"],
            ["receivables.company_id", "receivables.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "payable_id"],
            ["payables.company_id", "payables.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("num_nonnulls(receivable_id,payable_id)=1", name="target"),
        CheckConstraint("adjustment_type IN ('CREDIT_NOTE','DEBIT_NOTE')", name="type"),
        CheckConstraint("amount > 0 AND amount < 1000000000000000", name="amount"),
    )
