"""확정 파일을 재검증하고 모든 행을 하나의 작업단위에서 거래로 승격합니다."""

import re
from collections.abc import Callable
from uuid import UUID, uuid4

from app.accounting.transactions.application.service import TransactionService
from app.accounting.transactions.domain.entities import Transaction
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.identity.users.domain.entities import Principal
from app.intake.application.service import IntakeService
from app.intake.domain.canonical_fields import TargetContext
from app.intake.domain.digest import digest, row_digest
from app.intake.domain.entities import PromotionRow, Receipt
from app.intake.domain.errors import MappingRequired, PreviewStale, SourceConflict
from app.intake.domain.validation import validate
from app.intake.promotion.application.contracts import PromotionUnitOfWork
from app.intake.promotion.domain.mapper import map_row


class PromotionService:
    def __init__(self, factory: Callable[[], PromotionUnitOfWork], intake: IntakeService) -> None:
        self.factory = factory
        self.intake = intake

    def promote(
        self,
        actor: Principal,
        company: UUID,
        identifier: UUID,
        *,
        expected_version: int,
        receipt_id: UUID,
        source_digest: str,
        idempotency_key: str,
    ) -> Receipt:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", idempotency_key):
            raise InvalidInput()
        fingerprint = digest(
            [
                "import-promote-v1",
                str(identifier),
                str(receipt_id),
                source_digest,
                expected_version,
                "TRANSACTION_CANONICAL",
            ]
        )
        with self.factory() as uow:
            snapshot = self.intake._get(uow, actor, company, identifier, "import.confirm")
            require_company(uow, actor, company, "transaction.create")
            if snapshot.target_context != TargetContext.TRANSACTION_CANONICAL:
                raise StateConflict()
        # Preview TTL에는 의존하지 않고 확정된 파일·매핑을 다시 읽습니다.
        workbook = self.intake._workbook(snapshot)
        with self.factory() as uow:
            uow.promotions.lock_request(company, actor.user_id, idempotency_key)
            current = self.intake._get(uow, actor, company, identifier, "import.confirm")
            require_company(uow, actor, company, "transaction.create")
            replay = uow.promotions.replay(company, actor.user_id, idempotency_key, fingerprint)
            receipt = uow.imports.receipt(company_id=company, import_id=identifier)
            if receipt is None or receipt.id != receipt_id:
                raise ResourceNotFound()
            if (
                receipt.source_digest != source_digest
                or receipt.confirmed_version != expected_version
                or (snapshot.version != current.version and current.status != "COMPLETED")
                or current.version != receipt.confirmed_version + (1 if current.status == "COMPLETED" else 0)
                or snapshot.file_sha256 != current.file_sha256
            ):
                raise PreviewStale()
            mappings = [c.mapping for c in uow.imports.columns(current)]
            if self.intake._digest(current, mappings) != current.preview_digest:
                raise PreviewStale()
            records, errors = validate(workbook, current.source_type, mappings)
            actual = digest([row_digest(r) for r in sorted(records, key=lambda r: r.source_id)])
            if errors or not records:
                raise MappingRequired()
            if actual != receipt.source_digest:
                raise PreviewStale()
            if replay is not None or current.status == "COMPLETED":
                if receipt.status != "COMPLETED" or receipt.transaction_count != len(records):
                    raise StateConflict()
                if replay is None:
                    uow.promotions.record(
                        current, receipt, actor.user_id, idempotency_key, fingerprint, uow.now()
                    )
                return receipt
            if current.status != "CONFIRMED" or current.version != expected_version:
                raise StateConflict()
            evidence = uow.promotions.evidence(current)
            now = uow.now()
            results: list[PromotionRow] = []
            # 원천 잠금 순서를 고정해 여러 Import 사이의 역순 교착을 방지합니다.
            for record in sorted(records, key=lambda r: r.source_id):
                fact = map_row(current.source_type, record)
                counterparty = (
                    uow.counterparties.by_code(company_id=company, code=fact.counterparty_code)
                    if fact.counterparty_code
                    else None
                )
                review = (
                    "COUNTERPARTY_UNRESOLVED"
                    if (fact.counterparty_code or fact.counterparty_text)
                    and (counterparty is None or counterparty.status != "ACTIVE")
                    else None
                )
                old = uow.transactions.source(company, current.source_system, fact.source_id)
                if old is not None and old.source_fingerprint != fact.fingerprint:
                    raise SourceConflict()
                transaction = Transaction(
                    id=uuid4(),
                    company_id=company,
                    transaction_date=fact.transaction_date,
                    accounting_date=fact.accounting_date,
                    description=fact.description,
                    amount=fact.amount,
                    tax_amount=fact.tax_amount,
                    currency_code=fact.currency_code,
                    direction=fact.direction,
                    source_type=fact.source_type,
                    source_system=current.source_system,
                    source_id=fact.source_id,
                    source_fingerprint=fact.fingerprint,
                    payment_method=fact.payment_method,
                    status="NEEDS_INFORMATION" if review else "READY_FOR_ACCOUNTING",
                    version=1,
                    counterparty_id=counterparty.id if counterparty and not review else None,
                    import_id=current.id,
                    evidence_id=evidence,
                    created_by=actor.user_id,
                    created_at=now,
                    updated_at=now,
                )
                saved = TransactionService.save_in(uow, actor, transaction)
                results.append(
                    PromotionRow(
                        record.sheet_index,
                        record.row_number,
                        record.source_id,
                        row_digest(record),
                        saved.id,
                        "REUSED" if old else "CREATED",
                        review,
                    )
                )
            uow.promotions.finish(current, receipt, results, now)
            uow.promotions.record(
                current, receipt, actor.user_id, idempotency_key, fingerprint, now
            )
            result = uow.imports.receipt(company_id=company, import_id=identifier)
            assert result is not None
            return result
