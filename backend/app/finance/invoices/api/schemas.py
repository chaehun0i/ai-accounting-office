from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.finance.invoices.domain.entities import DocumentStatus, DocumentType


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineInput(StrictInput):
    line_no: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=500)
    supply_amount: Decimal = Field(ge=0, max_digits=19, decimal_places=4)
    tax_amount: Decimal = Field(ge=0, max_digits=19, decimal_places=4)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=19, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=19, decimal_places=4)

    @field_validator("supply_amount", "tax_amount", "quantity", "unit_price", mode="before")
    @classmethod
    def decimal_only(cls, value: object) -> object:
        if isinstance(value, (float, bool)):
            raise ValueError("금액과 수량은 정확한 십진수 문자열로 입력해 주세요.")
        return value


class InvoiceCreate(StrictInput):
    document_no: str = Field(min_length=1, max_length=100)
    counterparty_id: UUID
    issue_date: date
    accounting_date: date
    due_date: date
    currency_code: Literal["KRW"] = "KRW"
    source_system: str = Field(default="MANUAL", min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=100)
    source_import_id: UUID | None = None
    evidence_id: UUID | None = None
    lines: list[LineInput] = Field(min_length=1, max_length=500)


class InvoiceUpdate(InvoiceCreate):
    expected_version: int = Field(ge=1)


class NoteCreate(InvoiceCreate):
    original_document_type: Literal[DocumentType.SALES_INVOICE, DocumentType.PURCHASE_INVOICE]
    original_document_id: UUID
    reason_code: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=1)


class VersionCommand(StrictInput):
    expected_version: int = Field(ge=1)


class DocumentRead(BaseModel):
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
    lines: list[LineInput]
    original_document_type: DocumentType | None
    original_document_id: UUID | None
    reason_code: str | None
    transaction_id: UUID | None
    obligation_id: UUID | None
    source_import_id: UUID | None
    evidence_id: UUID | None
    approved_by: UUID | None
    approved_at: datetime | None
    supply_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
