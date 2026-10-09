"""회사 범위로 조회하고 flush만 수행하는 인테이크 영속성 어댑터입니다."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.evidence.infrastructure.models import EvidenceModel
from app.intake.domain.canonical_fields import Mapping, SourceType, TargetContext, normalize
from app.intake.domain.digest import row_digest
from app.intake.domain.entities import Column, Confirmation, Import, Receipt
from app.intake.domain.validation import CanonicalRow, ValidationError
from app.intake.domain.workbook import Workbook
from app.intake.infrastructure.models import (
    ImportColumnModel,
    ImportConfirmationModel,
    ImportEvidenceModel,
    ImportMappingModel,
    ImportModel,
    ImportReceiptModel,
    ImportSheetModel,
    ImportSourceRecordModel,
    ImportValidationErrorModel,
)
from app.storage.infrastructure.models import StorageObjectModel


def receipt_value(row: ImportReceiptModel) -> Receipt:
    return Receipt(
        row.id,
        row.company_id,
        row.import_id,
        row.source_digest,
        row.transaction_count,
        row.evidence_count,
        row.counterparty_count,
        row.status,
        row.created_at,
    )


class ImportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _row(self, company_id: UUID, resource_id: UUID) -> ImportModel | None:
        return self.session.scalar(
            select(ImportModel)
            .where(ImportModel.company_id == company_id, ImportModel.id == resource_id)
            .with_for_update()
        )

    def get(self, *, company_id: UUID, resource_id: UUID) -> Import | None:
        row = self._row(company_id, resource_id)
        if row is None:
            return None
        stored = self.session.scalar(
            select(StorageObjectModel).where(
                StorageObjectModel.company_id == company_id,
                StorageObjectModel.id == row.storage_object_id,
            )
        )
        assert stored is not None
        return Import(
            row.id,
            company_id,
            row.requested_by,
            row.storage_object_id,
            stored.storage_key,
            SourceType(row.source_type),
            TargetContext(row.target_context),
            row.source_system,
            row.original_filename,
            stored.content_type,
            row.file_sha256,
            row.status,
            row.version,
            row.mapping_version,
            row.preview_digest,
            row.preview_expires_at,
            row.created_at,
        )

    def add(self, value: Import, workbook: Workbook, mappings: list[Mapping], size: int) -> None:
        now = value.created_at
        self.session.add(
            StorageObjectModel(
                id=value.storage_object_id,
                company_id=value.company_id,
                storage_provider="LOCAL",
                storage_key=value.storage_key,
                original_filename=value.original_filename,
                content_type=value.content_type,
                size_bytes=size,
                sha256=value.file_sha256,
                status="AVAILABLE",
                created_by=value.requested_by,
                created_at=now,
            )
        )
        self.session.flush()
        self.session.add(
            ImportModel(
                id=value.id,
                company_id=value.company_id,
                source_type=value.source_type.value,
                target_context=value.target_context.value,
                source_system=value.source_system,
                storage_object_id=value.storage_object_id,
                original_filename=value.original_filename,
                file_sha256=value.file_sha256,
                status=value.status,
                detected_encoding=workbook.encoding,
                sheet_count=len(workbook.sheets),
                requested_by=value.requested_by,
                version=1,
                mapping_version=1,
                created_at=now,
                updated_at=now,
            )
        )
        evidence_id = uuid4()
        self.session.add(
            EvidenceModel(
                id=evidence_id,
                company_id=value.company_id,
                evidence_type="FILE",
                source_type=value.source_type.value,
                source_system=value.source_system,
                source_id=str(value.id),
                storage_object_id=value.storage_object_id,
                sha256=value.file_sha256,
                content_type=value.content_type,
                original_filename=value.original_filename,
                observed_at=now,
                ingested_at=now,
                created_by=value.requested_by,
                created_at=now,
            )
        )
        self.session.flush()
        self.session.add(
            ImportEvidenceModel(
                import_id=value.id,
                evidence_id=evidence_id,
                company_id=value.company_id,
                relation_type="SOURCE",
            )
        )
        for sheet in workbook.sheets:
            sheet_id = uuid4()
            self.session.add(
                ImportSheetModel(
                    id=sheet_id,
                    import_id=value.id,
                    sheet_index=sheet.index,
                    sheet_name=sheet.name,
                    row_count=len(sheet.rows),
                    column_count=len(sheet.headers),
                    status="PARSED",
                )
            )
            self.session.flush()
            for index, header in enumerate(sheet.headers):
                column_id = uuid4()
                mapping = next(
                    m for m in mappings if m.sheet_index == sheet.index and m.column_index == index
                )
                self.session.add(
                    ImportColumnModel(
                        id=column_id,
                        import_sheet_id=sheet_id,
                        column_index=index,
                        source_header=header,
                        normalized_header=normalize(header),
                        detected_type="TEXT",
                        sample_summary="원본 값은 저장하지 않습니다.",
                        is_required_candidate=False,
                    )
                )
                self.session.flush()
                self.session.add(
                    ImportMappingModel(
                        import_id=value.id,
                        import_sheet_id=sheet_id,
                        source_column_id=column_id,
                        canonical_field_code=mapping.canonical_field_code,
                        mapping_status=mapping.status,
                        confidence=Decimal("1")
                        if mapping.status == "EXACT"
                        else Decimal("0.9")
                        if mapping.status == "ALIAS_MATCH"
                        else Decimal("0"),
                    )
                )
        self.session.flush()

    def columns(self, value: Import) -> list[Column]:
        rows = self.session.execute(
            select(ImportSheetModel, ImportColumnModel, ImportMappingModel)
            .join(ImportColumnModel, ImportColumnModel.import_sheet_id == ImportSheetModel.id)
            .join(ImportMappingModel, ImportMappingModel.source_column_id == ImportColumnModel.id)
            .join(ImportModel, ImportModel.id == ImportSheetModel.import_id)
            .where(ImportModel.company_id == value.company_id, ImportModel.id == value.id)
            .order_by(ImportSheetModel.sheet_index, ImportColumnModel.column_index)
        )
        return [
            Column(
                s.sheet_index,
                s.sheet_name,
                c.column_index,
                c.source_header,
                Mapping(s.sheet_index, c.column_index, m.canonical_field_code, m.mapping_status),
            )
            for s, c, m in rows
        ]

    def map(self, value: Import, mappings: list[Mapping], actor: UUID, now: datetime) -> None:
        sheets = list(
            self.session.scalars(
                select(ImportSheetModel).where(ImportSheetModel.import_id == value.id)
            )
        )
        self.session.execute(
            delete(ImportMappingModel).where(ImportMappingModel.import_id == value.id)
        )
        for mapping in mappings:
            sheet = next(s for s in sheets if s.sheet_index == mapping.sheet_index)
            column = self.session.scalar(
                select(ImportColumnModel).where(
                    ImportColumnModel.import_sheet_id == sheet.id,
                    ImportColumnModel.column_index == mapping.column_index,
                )
            )
            assert column is not None
            self.session.add(
                ImportMappingModel(
                    import_id=value.id,
                    import_sheet_id=sheet.id,
                    source_column_id=column.id,
                    canonical_field_code=mapping.canonical_field_code,
                    mapping_status=mapping.status,
                    confidence=Decimal("1"),
                    confirmed_by=actor,
                    confirmed_at=now,
                )
            )
        row = self._row(value.company_id, value.id)
        assert row is not None
        row.mapping_version += 1
        row.version += 1
        row.status = "MAPPING_REQUIRED"
        row.preview_digest = None
        row.preview_expires_at = None
        row.updated_at = now
        self.session.execute(
            delete(ImportValidationErrorModel).where(
                ImportValidationErrorModel.import_id == value.id
            )
        )
        self.session.flush()

    def preview(
        self,
        value: Import,
        digest: str,
        expires: datetime,
        errors: list[ValidationError],
        now: datetime,
    ) -> None:
        row = self._row(value.company_id, value.id)
        assert row is not None
        row.preview_digest = digest
        row.preview_expires_at = expires
        row.version += 1
        row.updated_at = now
        row.status = "MAPPING_REQUIRED" if errors else "PREVIEW_READY"
        self.session.execute(
            delete(ImportValidationErrorModel).where(
                ImportValidationErrorModel.import_id == value.id
            )
        )
        sheets = {
            s.sheet_index: s.id
            for s in self.session.scalars(
                select(ImportSheetModel).where(ImportSheetModel.import_id == value.id)
            )
        }
        for error in errors:
            self.session.add(
                ImportValidationErrorModel(
                    import_id=value.id,
                    import_sheet_id=sheets[error.sheet_index],
                    row_number=error.row_number,
                    column_index=error.column_index,
                    error_code=error.error_code,
                    severity=error.severity,
                    message=error.message,
                    canonical_field_code=error.canonical_field_code,
                    created_at=now,
                )
            )
        self.session.flush()

    def errors(self, value: Import) -> list[ValidationError]:
        rows = self.session.execute(
            select(ImportValidationErrorModel, ImportSheetModel.sheet_index)
            .join(
                ImportSheetModel, ImportSheetModel.id == ImportValidationErrorModel.import_sheet_id
            )
            .join(ImportModel, ImportModel.id == ImportValidationErrorModel.import_id)
            .where(ImportModel.company_id == value.company_id, ImportModel.id == value.id)
            .order_by(
                ImportSheetModel.sheet_index,
                ImportValidationErrorModel.row_number,
                ImportValidationErrorModel.column_index,
            )
        )
        return [
            ValidationError(
                index,
                r.row_number,
                r.column_index,
                r.error_code,
                r.severity,
                r.message,
                r.canonical_field_code,
            )
            for r, index in rows
        ]

    def receipt(self, *, company_id: UUID, import_id: UUID) -> Receipt | None:
        row = self.session.scalar(
            select(ImportReceiptModel).where(
                ImportReceiptModel.company_id == company_id,
                ImportReceiptModel.import_id == import_id,
            )
        )
        return receipt_value(row) if row else None

    def replay(self, company_id: UUID, actor: UUID, key: str) -> Confirmation | None:
        result = self.session.execute(
            select(ImportConfirmationModel, ImportReceiptModel)
            .join(ImportReceiptModel, ImportReceiptModel.id == ImportConfirmationModel.receipt_id)
            .where(
                ImportConfirmationModel.company_id == company_id,
                ImportConfirmationModel.actor_id == actor,
                ImportConfirmationModel.idempotency_key == key,
            )
        ).first()
        return Confirmation(result[0].fingerprint, receipt_value(result[1])) if result else None

    def source(self, value: Import, source_id: str) -> str | None:
        return self.session.scalar(
            select(ImportSourceRecordModel.content_digest).where(
                ImportSourceRecordModel.company_id == value.company_id,
                ImportSourceRecordModel.source_type == value.source_type.value,
                ImportSourceRecordModel.target_context == value.target_context.value,
                ImportSourceRecordModel.source_system == value.source_system,
                ImportSourceRecordModel.source_id == source_id,
            )
        )

    def confirm(
        self,
        value: Import,
        receipt: Receipt,
        rows: list[CanonicalRow],
        actor: UUID,
        key: str,
        fingerprint: str,
        now: datetime,
    ) -> None:
        if self.receipt(company_id=value.company_id, import_id=value.id) is None:
            self.session.add(
                ImportReceiptModel(
                    **{field: getattr(receipt, field) for field in receipt.__dataclass_fields__}
                )
            )
            self.session.flush()
            for record in rows:
                if self.source(value, record.source_id) is None:
                    self.session.add(
                        ImportSourceRecordModel(
                            company_id=value.company_id,
                            source_type=value.source_type.value,
                            target_context=value.target_context.value,
                            source_system=value.source_system,
                            source_id=record.source_id,
                            content_digest=row_digest(record),
                            receipt_id=receipt.id,
                        )
                    )
        self.session.add(
            ImportConfirmationModel(
                company_id=value.company_id,
                actor_id=actor,
                import_id=value.id,
                idempotency_key=key,
                fingerprint=fingerprint,
                receipt_id=receipt.id,
                created_at=now,
            )
        )
        row = self._row(value.company_id, value.id)
        assert row is not None
        row.status = "COMPLETED"
        row.version += 1
        row.confirmed_at = now
        row.completed_at = now
        row.updated_at = now
        self.session.flush()
