"""문서 승인·거래·채권채무를 하나의 작업단위로 연결합니다."""

import builtins
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.accounting.journals.domain.errors import AccountingError
from app.accounting.transactions.application.service import TransactionService
from app.accounting.transactions.domain.entities import Transaction
from app.companies.application.service import require_company
from app.contracts.access_errors import ResourceNotFound, StateConflict, VersionConflict
from app.finance.invoices.application.contracts import DocumentUnitOfWork
from app.finance.invoices.domain.entities import Document, DocumentStatus, DocumentType
from app.finance.invoices.domain.rules import (
    document_fingerprint,
    require_transition,
    validate_correction,
    validate_document,
)
from app.finance.receivables.application.service import ObligationService
from app.finance.settlements.application.policy import fingerprint
from app.identity.users.domain.entities import Principal


class DocumentService:
    def __init__(self, factory: Callable[[], DocumentUnitOfWork]) -> None:
        self.factory = factory

    def list(self, actor: Principal, company: UUID, kind: DocumentType) -> builtins.list[Document]:
        with self.factory() as uow:
            require_company(uow, actor, company, "invoice.read")
            return uow.documents.list(company, kind)

    def get(self, actor: Principal, company: UUID, kind: DocumentType, resource: UUID) -> Document:
        with self.factory() as uow:
            require_company(uow, actor, company, "invoice.read")
            return self._get(uow, company, kind, resource)

    @staticmethod
    def _get(
        uow: DocumentUnitOfWork,
        company: UUID,
        kind: DocumentType,
        resource: UUID,
        *,
        lock: bool = False,
    ) -> Document:
        value = uow.documents.get(company, kind, resource, lock=lock)
        if value is None:
            raise ResourceNotFound()
        return value

    def save(
        self,
        actor: Principal,
        value: Document,
        key: str,
        expected_version: int | None = None,
        original_version: int | None = None,
    ) -> Document:
        validate_document(value)
        digest = document_fingerprint(value)
        command = (
            f"DOCUMENT_{'CREATE' if expected_version is None else 'UPDATE'}_{value.document_type}"
        )
        with self.factory() as uow:
            require_company(
                uow,
                actor,
                value.company_id,
                "credit_note.create" if value.is_note else "invoice.create",
            )
            uow.lock_command(value.company_id, actor.user_id, command, key)
            replay = uow.documents.replay(
                value.company_id,
                actor.user_id,
                command,
                key,
                fingerprint(digest, expected_version, original_version),
            )
            if replay:
                return self._get(uow, value.company_id, value.document_type, replay)
            uow.documents.lock_counterparty(value.company_id, value.counterparty_id)
            for kind, resource in [
                ("import", value.source_import_id),
                ("evidence", value.evidence_id),
            ]:
                if resource and not uow.reference_exists(value.company_id, kind, resource):
                    raise ResourceNotFound()
            before = ""
            old: Document | None = None
            if expected_version is not None:
                old = self._get(uow, value.company_id, value.document_type, value.id, lock=True)
                if old.version != expected_version:
                    raise VersionConflict()
                if old.status != DocumentStatus.DRAFT:
                    raise StateConflict()
                value = replace(
                    value,
                    created_at=old.created_at,
                    created_by=old.created_by,
                    version=old.version + 1,
                )
                before = old.status.value
            else:
                old = uow.documents.source(
                    value.company_id, value.document_type, value.source_system, value.source_id
                )
                if old:
                    if old.source_fingerprint != digest:
                        raise AccountingError(
                            "IMPORT_SOURCE_CONFLICT",
                            "같은 원천 식별자의 문서 내용이 다릅니다.",
                            409,
                        )
                    return old
            if value.is_note:
                assert value.original_document_type and value.original_document_id
                original = self._get(
                    uow,
                    value.company_id,
                    value.original_document_type,
                    value.original_document_id,
                    lock=True,
                )
                if original.version != original_version:
                    raise AccountingError(
                        "SOURCE_DOCUMENT_STALE", "원문서가 변경되었습니다. 다시 확인해 주세요.", 409
                    )
                assert original.transaction_id
                target = uow.obligations(original.kind).invoice_source(
                    value.company_id, original.transaction_id
                )
                if target is None:
                    raise ResourceNotFound()
                validate_correction(original, value, target.outstanding_amount)
            value = replace(value, source_fingerprint=digest)
            uow.documents.save(value, original_version)
            uow.documents.event(
                value,
                actor.user_id,
                command,
                key,
                fingerprint(digest, expected_version, original_version),
                before,
                datetime.now(UTC),
            )
            return value

    def transition(
        self,
        actor: Principal,
        company: UUID,
        kind: DocumentType,
        resource: UUID,
        action: str,
        expected_version: int,
        key: str,
    ) -> Document:
        command = f"DOCUMENT_{action.upper()}_{kind}"
        digest = fingerprint(kind, resource, expected_version)
        with self.factory() as uow:
            require_company(
                uow, actor, company, "invoice.approve" if action == "approve" else "invoice.review"
            )
            uow.lock_command(company, actor.user_id, command, key)
            replay = uow.documents.replay(company, actor.user_id, command, key, digest)
            if replay:
                return self._get(uow, company, kind, replay)
            value = self._get(uow, company, kind, resource, lock=True)
            if value.version != expected_version:
                raise VersionConflict()
            status = require_transition(value, action)
            validate_document(value)
            uow.documents.lock_counterparty(company, value.counterparty_id)
            now = datetime.now(UTC)
            result = replace(value, status=status, version=value.version + 1, updated_at=now)
            if action == "approve":
                if actor.user_id == value.created_by:
                    raise AccountingError(
                        "SELF_APPROVAL_NOT_ALLOWED",
                        "작성자와 다른 승인 담당자가 확인해 주세요.",
                        409,
                    )
                original = None
                target = None
                if value.is_note:
                    assert value.original_document_type and value.original_document_id
                    original = self._get(
                        uow,
                        company,
                        value.original_document_type,
                        value.original_document_id,
                        lock=True,
                    )
                    if original.version != uow.documents.original_version(company, value.id):
                        raise AccountingError(
                            "SOURCE_DOCUMENT_STALE", "원문서가 변경되었습니다.", 409
                        )
                    assert original.transaction_id
                    target = uow.obligations(value.kind).invoice_source(
                        company, original.transaction_id
                    )
                    if target is None:
                        raise ResourceNotFound()
                    validate_correction(original, value, target.outstanding_amount)
                direction = "INFLOW" if value.kind == "AR" else "OUTFLOW"
                if kind == DocumentType.CREDIT_NOTE:
                    direction = "OUTFLOW" if direction == "INFLOW" else "INFLOW"
                transaction = TransactionService.from_approved_document_in(
                    uow,
                    actor,
                    Transaction(
                        id=uuid4(),
                        company_id=company,
                        transaction_date=value.issue_date,
                        accounting_date=value.accounting_date,
                        description=value.document_no,
                        amount=value.total_amount,
                        tax_amount=value.tax_amount,
                        currency_code=value.currency_code,
                        direction=direction,
                        source_type="BUSINESS_DOCUMENT",
                        source_system="BUSINESS_DOCUMENT",
                        source_id=f"{kind}:{value.id}",
                        source_fingerprint=value.source_fingerprint,
                        status="READY_FOR_ACCOUNTING",
                        version=1,
                        created_by=actor.user_id,
                        created_at=now,
                        updated_at=now,
                        counterparty_id=value.counterparty_id,
                        import_id=value.source_import_id,
                        evidence_id=value.evidence_id,
                    ),
                )
                result = replace(
                    result,
                    transaction_id=transaction.id,
                    approved_by=actor.user_id,
                    approved_at=now,
                )
                # 정정 사실 FK는 문서 승인 저장 뒤에 생성하되 전체 작업은 함께 rollback됩니다.
                uow.documents.save(result)
                if target:
                    ObligationService.adjust_invoice_in(
                        uow,
                        actor,
                        company,
                        value.kind,
                        target.id,
                        value.id,
                        kind.value,
                        value.total_amount,
                        value.accounting_date,
                    )
                    result = replace(result, obligation_id=target.id)
                else:
                    obligation_id = ObligationService.recognize_invoice_in(
                        uow,
                        actor,
                        company,
                        value.kind,
                        value.id,
                        transaction.id,
                        value.counterparty_id,
                        value.total_amount,
                        value.due_date,
                        value.accounting_date,
                    )
                    result = replace(result, obligation_id=obligation_id)
            else:
                uow.documents.save(result)
            uow.documents.event(
                result, actor.user_id, command, key, digest, value.status.value, now
            )
            return result
