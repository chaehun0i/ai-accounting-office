"""승격 참조만 저장하며 transaction boundary는 Application에 위임합니다."""

from dataclasses import asdict
from datetime import datetime
from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.contracts.access_errors import ResourceNotFound
from app.intake.domain.entities import Import, Receipt, PromotionRow
from app.intake.domain.errors import IdempotencyConflict
from app.intake.infrastructure.models import ImportModel, ImportReceiptModel, ImportEvidenceModel
from app.intake.promotion.infrastructure.models import (
    ImportPromotionCommandModel,
    ImportPromotionRowModel,
)


class PromotionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_request(self, company: UUID, actor: UUID, key: str) -> None:
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
            {"identity": f"import-promote:{company}:{actor}:{key}"},
        )

    def replay(self, company: UUID, actor: UUID, key: str, fingerprint: str) -> UUID | None:
        row = self.session.scalar(
            select(ImportPromotionCommandModel).where(
                ImportPromotionCommandModel.company_id == company,
                ImportPromotionCommandModel.actor_id == actor,
                ImportPromotionCommandModel.command_code == "IMPORT_PROMOTE",
                ImportPromotionCommandModel.idempotency_key == key,
            )
        )
        if row and row.fingerprint != fingerprint:
            raise IdempotencyConflict()
        return row.receipt_id if row else None

    def evidence(self, value: Import) -> UUID:
        result = self.session.scalar(
            select(ImportEvidenceModel.evidence_id).where(
                ImportEvidenceModel.company_id == value.company_id,
                ImportEvidenceModel.import_id == value.id,
                ImportEvidenceModel.relation_type == "SOURCE",
            )
        )
        if result is None:
            raise ResourceNotFound()
        return result

    def finish(
        self, value: Import, receipt: Receipt, rows: list[PromotionRow], now: datetime
    ) -> None:
        parent = self.session.scalar(
            select(ImportModel)
            .where(ImportModel.company_id == value.company_id, ImportModel.id == value.id)
            .with_for_update()
        )
        result = self.session.scalar(
            select(ImportReceiptModel)
            .where(
                ImportReceiptModel.company_id == value.company_id,
                ImportReceiptModel.id == receipt.id,
            )
            .with_for_update()
        )
        assert parent is not None and result is not None
        parent.status = "IMPORTING"
        self.session.flush()
        for row in rows:
            self.session.add(
                ImportPromotionRowModel(
                    company_id=value.company_id,
                    import_id=value.id,
                    receipt_id=receipt.id,
                    promoted_at=now,
                    **asdict(row),
                )
            )
        result.transaction_count = len(rows)
        result.status = "COMPLETED"
        result.promoted_at = now
        parent.status = "COMPLETED"
        parent.version += 1
        parent.completed_at = now
        parent.updated_at = now
        self.session.flush()

    def record(
        self,
        value: Import,
        receipt: Receipt,
        actor: UUID,
        key: str,
        fingerprint: str,
        now: datetime,
    ) -> None:
        self.session.add(
            ImportPromotionCommandModel(
                company_id=value.company_id,
                actor_id=actor,
                idempotency_key=key,
                fingerprint=fingerprint,
                import_id=value.id,
                receipt_id=receipt.id,
                created_at=now,
            )
        )
        self.session.flush()
