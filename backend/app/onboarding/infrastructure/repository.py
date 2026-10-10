"""회사 잠금 아래 초안과 출처 이력을 저장하며 commit은 UoW에 맡깁니다."""

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.contracts.access_errors import VersionConflict
from app.intake.domain.entities import Import
from app.onboarding.domain.catalog import BY_CODE, CATALOG, REQUIRED_SECTIONS, SECTIONS
from app.onboarding.domain.entities import ImportLink, Receipt, Workspace
from app.onboarding.domain.validation import Issue, progress
from app.onboarding.domain.values import Cell, Scalar
from app.onboarding.infrastructure.models import (
    ApplyReceiptModel,
    FieldDefinitionModel,
    OnboardingImportModel,
    OnboardingSessionModel,
    PromotionReceiptModel,
    RowItemModel,
    SectionModel,
    ValidationResultModel,
    ValueHistoryModel,
    ValueModel,
)


def field_id(code: str) -> UUID:
    return uuid5(NAMESPACE_URL, "ai-accounting-office:onboarding:v1:" + code)


def typed_columns(value: Scalar) -> dict[str, Scalar | None]:
    result: dict[str, Scalar | None] = dict.fromkeys(
        ("value_text", "value_numeric", "value_date", "value_boolean")
    )
    kind = (
        "value_boolean"
        if type(value) is bool
        else "value_numeric"
        if isinstance(value, Decimal)
        else "value_date"
        if isinstance(value, date)
        else "value_text"
    )
    result[kind] = value
    return result


def scalar(row: ValueModel) -> Scalar:
    for value in (row.value_text, row.value_numeric, row.value_date, row.value_boolean):
        if value is not None:
            return value
    raise RuntimeError("형식이 지정된 값이 필요합니다.")


class OnboardingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, company_id: UUID) -> Workspace | None:
        row = self.session.scalar(
            select(OnboardingSessionModel)
            .where(OnboardingSessionModel.company_id == company_id)
            .with_for_update()
        )
        if row is None:
            return None
        cells = [
            Cell(f.field_code, v.row_key, scalar(v), v.source_type, v.status, v.version)
            for v, f in self.session.execute(
                select(ValueModel, FieldDefinitionModel)
                .join(
                    FieldDefinitionModel, FieldDefinitionModel.id == ValueModel.field_definition_id
                )
                .where(ValueModel.company_id == company_id, ValueModel.session_id == row.id)
                .order_by(FieldDefinitionModel.field_code, ValueModel.row_key)
            )
        ]
        return Workspace(row.id, company_id, row.status, row.version, cells)

    def start(self, company_id: UUID, actor: UUID, now: datetime) -> Workspace:
        # 고정 UUID와 불변 definition을 비교하여 seed drift를 조용히 덮어쓰지 않습니다.
        for field in CATALOG:
            identifier = field_id(field.field_code)
            definition = self.session.get(FieldDefinitionModel, identifier)
            if definition is None:
                self.session.add(FieldDefinitionModel(id=identifier, **asdict(field)))
            elif any(getattr(definition, key) != value for key, value in asdict(field).items()):
                raise RuntimeError("필드 카탈로그 버전과 등록 값이 다릅니다.")
        identifier = uuid4()
        self.session.add(
            OnboardingSessionModel(
                id=identifier,
                company_id=company_id,
                status="IN_PROGRESS",
                current_step="Company",
                started_by=actor,
                started_at=now,
                version=1,
            )
        )
        self.session.flush()
        for order, section in enumerate(SECTIONS):
            self.session.add(
                SectionModel(
                    id=uuid4(),
                    company_id=company_id,
                    session_id=identifier,
                    section_code=section,
                    status="EMPTY",
                    display_order=order,
                    required=section in REQUIRED_SECTIONS,
                )
            )
        self.session.flush()
        return Workspace(identifier, company_id, "IN_PROGRESS", 1, [])

    def save(
        self,
        workspace: Workspace,
        cells: list[Cell],
        actor: UUID,
        now: datetime,
        source_import: UUID | None = None,
        status: str = "IN_PROGRESS",
    ) -> Workspace:
        row = self.session.scalar(
            select(OnboardingSessionModel)
            .where(
                OnboardingSessionModel.company_id == workspace.company_id,
                OnboardingSessionModel.id == workspace.id,
            )
            .with_for_update()
        )
        if row is None or row.version != workspace.version:
            raise VersionConflict()
        for cell in cells:
            field = BY_CODE[cell.field_code]
            existing_item = self.session.scalar(
                select(RowItemModel).where(
                    RowItemModel.company_id == workspace.company_id,
                    RowItemModel.session_id == workspace.id,
                    RowItemModel.section_code == field.section_code,
                    RowItemModel.row_key == cell.row_key,
                )
            )
            if existing_item is None:
                self.session.add(
                    RowItemModel(
                        id=uuid4(),
                        company_id=workspace.company_id,
                        session_id=workspace.id,
                        section_code=field.section_code,
                        row_key=cell.row_key,
                    )
                )
                self.session.flush()
            current = self.session.scalar(
                select(ValueModel).where(
                    ValueModel.company_id == workspace.company_id,
                    ValueModel.session_id == workspace.id,
                    ValueModel.field_definition_id == field_id(cell.field_code),
                    ValueModel.row_key == cell.row_key,
                )
            )
            if current and (scalar(current), current.source_type, current.status) == (
                cell.value,
                cell.source_type,
                cell.status,
            ):
                continue
            if current:
                self.session.add(
                    ValueHistoryModel(
                        id=uuid4(),
                        company_id=workspace.company_id,
                        session_id=workspace.id,
                        value_id=current.id,
                        version=current.version,
                        updated_by=current.updated_by,
                        updated_at=current.updated_at,
                        source_type=current.source_type,
                        source_import_id=current.source_import_id,
                        **typed_columns(scalar(current)),
                    )
                )
                current.version += 1
            else:
                current = ValueModel(
                    id=uuid4(),
                    company_id=workspace.company_id,
                    session_id=workspace.id,
                    field_definition_id=field_id(cell.field_code),
                    section_code=field.section_code,
                    row_key=cell.row_key,
                    version=1,
                )
                self.session.add(current)
            for key, value in typed_columns(cell.value).items():
                setattr(current, key, value)
            current.source_type = cell.source_type
            # 기존 Excel provenance는 변경 전 history에 남깁니다.
            current.source_import_id = (
                source_import
                if cell.source_type == "EXCEL_IMPORT" and source_import
                else current.source_import_id
                if cell.source_type == "EXCEL_IMPORT"
                else None
            )
            current.status = cell.status
            current.updated_by, current.updated_at = actor, now
        row.version += 1
        row.status = status
        if status == "COMPLETED":
            row.completed_at = now
        for section in self.session.scalars(
            select(SectionModel).where(
                SectionModel.company_id == workspace.company_id,
                SectionModel.session_id == workspace.id,
            )
        ):
            section.status = progress(cells, section.section_code)[2]
        self.session.flush()
        result = self.get(company_id=workspace.company_id)
        assert result is not None
        return result

    def validation(self, workspace: Workspace, issues: list[Issue], now: datetime) -> None:
        self.session.execute(
            delete(ValidationResultModel).where(
                ValidationResultModel.company_id == workspace.company_id,
                ValidationResultModel.session_id == workspace.id,
            )
        )
        for issue in issues:
            self.session.add(
                ValidationResultModel(
                    id=uuid4(),
                    company_id=workspace.company_id,
                    session_id=workspace.id,
                    field_definition_id=field_id(issue.field_code) if issue.field_code else None,
                    row_key=issue.row_key,
                    validation_code=issue.validation_code,
                    severity=issue.severity,
                    status="OPEN",
                    message=issue.message,
                    created_at=now,
                )
            )
        self.session.flush()

    def link(self, workspace: Workspace, value: Import, metadata: dict[str, str]) -> ImportLink:
        self.session.add(
            OnboardingImportModel(
                id=uuid4(),
                company_id=workspace.company_id,
                session_id=workspace.id,
                import_id=value.id,
                template_code=metadata["template_code"],
                template_version=metadata["template_version"],
                schema_version=metadata["schema_version"],
                generated_at=datetime.fromisoformat(metadata["generated_at"]),
                locale=metadata["locale"],
                status="UPLOADED",
            )
        )
        self.session.flush()
        return ImportLink(
            value.id,
            workspace.id,
            "UPLOADED",
            metadata["template_code"],
            metadata["template_version"],
        )

    def import_link(self, company_id: UUID, import_id: UUID) -> ImportLink | None:
        row = self.session.scalar(
            select(OnboardingImportModel).where(
                OnboardingImportModel.company_id == company_id,
                OnboardingImportModel.import_id == import_id,
            )
        )
        return (
            None
            if row is None
            else ImportLink(
                import_id, row.session_id, row.status, row.template_code, row.template_version
            )
        )

    def receipt(self, company_id: UUID, key: str, *, promotion: bool = False) -> Receipt | None:
        if promotion:
            row = self.session.scalar(
                select(PromotionReceiptModel).where(
                    PromotionReceiptModel.company_id == company_id,
                    PromotionReceiptModel.idempotency_key == key,
                )
            )
            return (
                None
                if row is None
                else Receipt(
                    row.id,
                    row.session_id,
                    None,
                    row.fingerprint,
                    row.account_count,
                    row.counterparty_count,
                    0,
                    0,
                    0,
                    row.created_at,
                )
            )
        applied = self.session.scalar(
            select(ApplyReceiptModel).where(
                ApplyReceiptModel.company_id == company_id, ApplyReceiptModel.idempotency_key == key
            )
        )
        return (
            None
            if applied is None
            else Receipt(
                applied.id,
                applied.session_id,
                applied.import_id,
                applied.fingerprint,
                applied.new_count,
                applied.changed_count,
                applied.unchanged_count,
                applied.conflict_count,
                applied.error_count,
                applied.created_at,
            )
        )

    def record(
        self, workspace: Workspace, receipt: Receipt, key: str, *, promotion: bool = False
    ) -> None:
        if promotion:
            self.session.add(
                PromotionReceiptModel(
                    id=receipt.id,
                    company_id=workspace.company_id,
                    session_id=workspace.id,
                    idempotency_key=key,
                    fingerprint=receipt.fingerprint,
                    account_count=receipt.new_count,
                    counterparty_count=receipt.changed_count,
                    created_at=receipt.created_at,
                )
            )
        else:
            self.session.add(
                ApplyReceiptModel(
                    id=receipt.id,
                    company_id=workspace.company_id,
                    session_id=workspace.id,
                    import_id=receipt.import_id,
                    idempotency_key=key,
                    fingerprint=receipt.fingerprint,
                    source_digest=receipt.fingerprint,
                    new_count=receipt.new_count,
                    changed_count=receipt.changed_count,
                    unchanged_count=receipt.unchanged_count,
                    conflict_count=receipt.conflict_count,
                    error_count=receipt.error_count,
                    created_at=receipt.created_at,
                )
            )
            row = self.session.scalar(
                select(OnboardingImportModel).where(
                    OnboardingImportModel.company_id == workspace.company_id,
                    OnboardingImportModel.import_id == receipt.import_id,
                )
            )
            assert row is not None
            row.status = "APPLIED"
        self.session.flush()
