from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.finance.invoices.api.schemas import (
    DocumentRead,
    InvoiceCreate,
    InvoiceUpdate,
    NoteCreate,
    VersionCommand,
)
from app.finance.invoices.application.service import DocumentService
from app.finance.invoices.domain.entities import (
    Document,
    DocumentLine,
    DocumentStatus,
    DocumentType,
)
from app.identity.auth.api.dependencies import csrf


def documents(container: Container) -> DocumentService:
    if container.documents is None:
        raise DatabaseUnavailable()
    return container.documents


Service = Annotated[DocumentService, Depends(documents)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


def response(value: Document) -> DocumentRead:
    return DocumentRead.model_validate(
        {
            **asdict(value),
            "supply_amount": value.supply_amount,
            "tax_amount": value.tax_amount,
            "total_amount": value.total_amount,
        }
    )


def draft(
    payload: InvoiceCreate,
    actor: Actor,
    company: UUID,
    kind: DocumentType,
    resource: UUID | None = None,
) -> Document:
    fields = payload.model_dump(exclude={"lines", "expected_version"})
    now = datetime.now(UTC)
    return Document(
        **fields,
        id=resource or uuid4(),
        company_id=company,
        document_type=kind,
        status=DocumentStatus.DRAFT,
        source_fingerprint="",
        version=1,
        created_by=actor.user_id,
        created_at=now,
        updated_at=now,
        lines=tuple(DocumentLine(**line.model_dump()) for line in payload.lines),
    )


def build_router(kind: DocumentType, prefix: str, note: bool = False) -> APIRouter:
    result = APIRouter(prefix=prefix, tags=["매출·매입 업무문서"])

    @result.get("", response_model=list[DocumentRead])
    def listing(actor: Actor, company_id: CompanyScope, service: Service) -> list[DocumentRead]:
        return [response(value) for value in service.list(actor, company_id, kind)]

    @result.get("/{resource_id}", response_model=DocumentRead)
    def detail(
        resource_id: UUID, actor: Actor, company_id: CompanyScope, service: Service
    ) -> DocumentRead:
        return response(service.get(actor, company_id, kind, resource_id))

    if note:

        @result.post("", response_model=DocumentRead, status_code=201, dependencies=[Depends(csrf)])
        def create_note(
            payload: NoteCreate, actor: Actor, company_id: CompanyScope, service: Service, key: Key
        ) -> DocumentRead:
            return response(
                service.save(
                    actor,
                    draft(payload, actor, company_id, kind),
                    key,
                    original_version=payload.expected_version,
                )
            )
    else:

        @result.post("", response_model=DocumentRead, status_code=201, dependencies=[Depends(csrf)])
        def create(
            payload: InvoiceCreate,
            actor: Actor,
            company_id: CompanyScope,
            service: Service,
            key: Key,
        ) -> DocumentRead:
            return response(service.save(actor, draft(payload, actor, company_id, kind), key))

        @result.patch("/{resource_id}", response_model=DocumentRead, dependencies=[Depends(csrf)])
        def update(
            resource_id: UUID,
            payload: InvoiceUpdate,
            actor: Actor,
            company_id: CompanyScope,
            service: Service,
            key: Key,
        ) -> DocumentRead:
            return response(
                service.save(
                    actor,
                    draft(payload, actor, company_id, kind, resource_id),
                    key,
                    payload.expected_version,
                )
            )

    @result.post("/{resource_id}/submit", response_model=DocumentRead, dependencies=[Depends(csrf)])
    def submit(
        resource_id: UUID,
        payload: VersionCommand,
        actor: Actor,
        company_id: CompanyScope,
        service: Service,
        key: Key,
    ) -> DocumentRead:
        return response(
            service.transition(
                actor, company_id, kind, resource_id, "submit", payload.expected_version, key
            )
        )

    @result.post(
        "/{resource_id}/approve", response_model=DocumentRead, dependencies=[Depends(csrf)]
    )
    def approve(
        resource_id: UUID,
        payload: VersionCommand,
        actor: Actor,
        company_id: CompanyScope,
        service: Service,
        key: Key,
    ) -> DocumentRead:
        return response(
            service.transition(
                actor, company_id, kind, resource_id, "approve", payload.expected_version, key
            )
        )

    return result


router = APIRouter()
for document_type, path in [
    (DocumentType.SALES_INVOICE, "/sales-invoices"),
    (DocumentType.PURCHASE_INVOICE, "/purchase-invoices"),
    (DocumentType.CREDIT_NOTE, "/credit-notes"),
    (DocumentType.DEBIT_NOTE, "/debit-notes"),
]:
    router.include_router(build_router(document_type, path, "NOTE" in document_type.value))
