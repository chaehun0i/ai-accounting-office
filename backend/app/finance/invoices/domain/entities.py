"""업무문서는 거래·전표와 별개의 경제적 원천입니다."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class DocumentType(StrEnum):
    SALES_INVOICE = "SALES_INVOICE"
    PURCHASE_INVOICE = "PURCHASE_INVOICE"
    CREDIT_NOTE = "CREDIT_NOTE"
    DEBIT_NOTE = "DEBIT_NOTE"


class DocumentStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"


@dataclass(frozen=True, kw_only=True)
class DocumentLine:
    line_no: int
    description: str
    supply_amount: Decimal
    tax_amount: Decimal
    quantity: Decimal | None = None
    unit_price: Decimal | None = None

    @property
    def total_amount(self) -> Decimal:
        return self.supply_amount + self.tax_amount


@dataclass(frozen=True, kw_only=True)
class Document:
    id: UUID
    company_id: UUID
    document_type: DocumentType
    document_no: str
    counterparty_id: UUID
    issue_date: date
    accounting_date: date
    due_date: date
    currency_code: str
    source_system: str
    source_id: str
    source_fingerprint: str
    status: DocumentStatus
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    lines: tuple[DocumentLine, ...]
    original_document_type: DocumentType | None = None
    original_document_id: UUID | None = None
    reason_code: str | None = None
    transaction_id: UUID | None = None
    obligation_id: UUID | None = None
    source_import_id: UUID | None = None
    evidence_id: UUID | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None

    @property
    def supply_amount(self) -> Decimal:
        return sum((line.supply_amount for line in self.lines), Decimal(0))

    @property
    def tax_amount(self) -> Decimal:
        return sum((line.tax_amount for line in self.lines), Decimal(0))

    @property
    def total_amount(self) -> Decimal:
        return self.supply_amount + self.tax_amount

    @property
    def is_note(self) -> bool:
        return self.document_type in {DocumentType.CREDIT_NOTE, DocumentType.DEBIT_NOTE}

    @property
    def kind(self) -> str:
        origin = self.original_document_type if self.is_note else self.document_type
        return "AR" if origin == DocumentType.SALES_INVOICE else "AP"
