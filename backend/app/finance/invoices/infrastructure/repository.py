"""회사 범위를 필수로 적용하고 원천·요청 잠금을 제공합니다."""

import builtins
from dataclasses import asdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.contracts.access_errors import ResourceNotFound
from app.finance.invoices.domain.entities import (
    Document,
    DocumentLine,
    DocumentStatus,
    DocumentType,
)
from app.finance.invoices.infrastructure.models import (
    DocumentColumns,
    DocumentEventModel,
    DocumentNoteLineModel,
    DocumentNoteModel,
    PurchaseInvoiceLineModel,
    PurchaseInvoiceModel,
    SalesInvoiceLineModel,
    SalesInvoiceModel,
)
from app.finance.payables.infrastructure.models import PayableModel
from app.finance.receivables.infrastructure.models import ReceivableModel
from app.intake.domain.errors import IdempotencyConflict
from app.master_data.counterparties.infrastructure.models import CounterpartyModel

Header = SalesInvoiceModel | PurchaseInvoiceModel | DocumentNoteModel


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def models(
        kind: DocumentType,
    ) -> tuple[
        type[SalesInvoiceModel] | type[PurchaseInvoiceModel] | type[DocumentNoteModel],
        type[SalesInvoiceLineModel] | type[PurchaseInvoiceLineModel] | type[DocumentNoteLineModel],
    ]:
        if kind == DocumentType.SALES_INVOICE:
            return SalesInvoiceModel, SalesInvoiceLineModel
        if kind == DocumentType.PURCHASE_INVOICE:
            return PurchaseInvoiceModel, PurchaseInvoiceLineModel
        return DocumentNoteModel, DocumentNoteLineModel

    def entity(
        self,
        row: DocumentColumns,
        kind: DocumentType,
        *,
        loaded_lines: tuple[DocumentLine, ...] | None = None,
        loaded_obligations: dict[UUID, UUID] | None = None,
    ) -> Document:
        _, line_model = self.models(kind)
        lines = (
            loaded_lines
            if loaded_lines is not None
            else tuple(
                DocumentLine(
                    **{key: getattr(line, key) for key in DocumentLine.__dataclass_fields__}
                )
                for line in self.session.scalars(
                    select(line_model)
                    .where(line_model.company_id == row.company_id, line_model.invoice_id == row.id)
                    .order_by(line_model.line_no)
                )
            )
        )
        fields = {
            key: getattr(row, key)
            for key in Document.__dataclass_fields__
            if hasattr(row, key) and key not in {"lines", "status", "document_type"}
        }
        if isinstance(row, DocumentNoteModel):
            fields.update(
                original_document_id=row.sales_invoice_id or row.purchase_invoice_id,
                original_document_type=DocumentType.SALES_INVOICE
                if row.sales_invoice_id
                else DocumentType.PURCHASE_INVOICE,
            )
        obligation_model = (
            ReceivableModel
            if kind == DocumentType.SALES_INVOICE
            or (isinstance(row, DocumentNoteModel) and row.sales_invoice_id)
            else PayableModel
        )
        invoice_id = (
            (row.sales_invoice_id or row.purchase_invoice_id)
            if isinstance(row, DocumentNoteModel)
            else row.id
        )
        fields["obligation_id"] = (
            loaded_obligations.get(invoice_id)
            if loaded_obligations is not None
            else self.session.scalar(
                select(obligation_model.id).where(
                    obligation_model.company_id == row.company_id,
                    obligation_model.source_invoice_id == invoice_id,
                )
            )
        )
        return Document(
            **fields, document_type=kind, status=DocumentStatus(row.status), lines=lines
        )

    def get(
        self, company: UUID, kind: DocumentType, resource: UUID, *, lock: bool = False
    ) -> Document | None:
        model, _ = self.models(kind)
        query = select(model).where(model.company_id == company, model.id == resource)
        if model is DocumentNoteModel:
            query = query.where(DocumentNoteModel.note_type == kind.value)
        row = self.session.scalar(query.with_for_update() if lock else query)
        return self.entity(row, kind) if row else None

    def list(self, company: UUID, kind: DocumentType) -> builtins.list[Document]:
        model, line_model = self.models(kind)
        query = select(model).where(model.company_id == company)
        if model is DocumentNoteModel:
            query = query.where(DocumentNoteModel.note_type == kind.value)
        rows = list(
            self.session.scalars(query.order_by(model.issue_date.desc(), model.id).limit(500))
        )
        if not rows:
            return []
        # 목록은 문서 수와 무관하게 항목과 연결을 묶어 읽습니다.
        ids = [row.id for row in rows]
        grouped: dict[UUID, builtins.list[DocumentLine]] = {resource: [] for resource in ids}
        for line in self.session.scalars(
            select(line_model)
            .where(line_model.company_id == company, line_model.invoice_id.in_(ids))
            .order_by(line_model.invoice_id, line_model.line_no)
        ):
            grouped[line.invoice_id].append(
                DocumentLine(
                    **{key: getattr(line, key) for key in DocumentLine.__dataclass_fields__}
                )
            )
        original_ids = [
            (row.sales_invoice_id or row.purchase_invoice_id)
            if isinstance(row, DocumentNoteModel)
            else row.id
            for row in rows
        ]
        obligations: dict[UUID, UUID] = {}
        for target in (ReceivableModel, PayableModel):
            obligations.update(
                dict(
                    self.session.execute(
                        select(target.source_invoice_id, target.id).where(
                            target.company_id == company, target.source_invoice_id.in_(original_ids)
                        )
                    ).all()
                )
            )
        return [
            self.entity(
                row, kind, loaded_lines=tuple(grouped[row.id]), loaded_obligations=obligations
            )
            for row in rows
        ]

    def source(
        self, company: UUID, kind: DocumentType, system: str, source_id: str
    ) -> Document | None:
        model, _ = self.models(kind)
        row = self.session.scalar(
            select(model)
            .where(
                model.company_id == company,
                model.source_system == system,
                model.source_id == source_id,
            )
            .with_for_update()
        )
        return (
            self.entity(
                row, DocumentType(row.note_type) if isinstance(row, DocumentNoteModel) else kind
            )
            if row
            else None
        )

    def save(self, value: Document, original_version: int | None = None) -> None:
        model, lines = self.models(value.document_type)
        row = self.session.scalar(
            select(model).where(model.company_id == value.company_id, model.id == value.id)
        )
        new = row is None
        if row is None:
            row = model()
            self.session.add(row)
        for key in Document.__dataclass_fields__:
            if hasattr(model, key) and key not in {"lines", "status"}:
                setattr(row, key, getattr(value, key))
        row.status = value.status.value
        row.supply_amount, row.tax_amount, row.total_amount = (
            value.supply_amount,
            value.tax_amount,
            value.total_amount,
        )
        if isinstance(row, DocumentNoteModel):
            row.note_type = value.document_type.value
            row.sales_invoice_id = value.original_document_id if value.kind == "AR" else None
            row.purchase_invoice_id = value.original_document_id if value.kind == "AP" else None
            row.original_version = (
                original_version if original_version is not None else row.original_version
            )
        self.session.flush()
        if new or value.status == DocumentStatus.DRAFT:
            self.session.execute(
                delete(lines).where(
                    lines.company_id == value.company_id, lines.invoice_id == value.id
                )
            )
            for line in value.lines:
                self.session.add(
                    lines(
                        id=uuid4(), company_id=value.company_id, invoice_id=value.id, **asdict(line)
                    )
                )
            self.session.flush()

    def original_version(self, company: UUID, resource: UUID) -> int:
        value = self.session.scalar(
            select(DocumentNoteModel.original_version).where(
                DocumentNoteModel.company_id == company, DocumentNoteModel.id == resource
            )
        )
        if value is None:
            raise ResourceNotFound()
        return value

    def replay(
        self, company: UUID, actor: UUID, command: str, key: str, fingerprint: str
    ) -> UUID | None:
        row = self.session.scalar(
            select(DocumentEventModel).where(
                DocumentEventModel.company_id == company,
                DocumentEventModel.actor_id == actor,
                DocumentEventModel.command_code == command,
                DocumentEventModel.idempotency_key == key,
            )
        )
        if row and row.fingerprint != fingerprint:
            raise IdempotencyConflict()
        return (
            row.sales_invoice_id or row.purchase_invoice_id or row.document_note_id if row else None
        )

    def event(
        self,
        value: Document,
        actor: UUID,
        command: str,
        key: str,
        fingerprint: str,
        before: str,
        now: datetime,
    ) -> None:
        field = (
            "document_note_id"
            if value.is_note
            else "sales_invoice_id"
            if value.kind == "AR"
            else "purchase_invoice_id"
        )
        self.session.add(
            DocumentEventModel(
                id=uuid4(),
                company_id=value.company_id,
                actor_id=actor,
                command_code=command,
                idempotency_key=key,
                fingerprint=fingerprint,
                before_status=before,
                after_status=value.status.value,
                result_version=value.version,
                created_at=now,
                **{field: value.id},
            )
        )
        self.session.flush()

    def lock_counterparty(self, company: UUID, resource: UUID) -> None:
        row = self.session.scalar(
            select(CounterpartyModel)
            .where(CounterpartyModel.company_id == company, CounterpartyModel.id == resource)
            .with_for_update()
        )
        if row is None or row.status != "ACTIVE":
            raise ResourceNotFound()
