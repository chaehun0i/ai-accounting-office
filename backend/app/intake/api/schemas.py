from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.intake.domain.canonical_fields import SourceType, TargetContext


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UploadCommand(Command):
    source_type: SourceType
    target_context: TargetContext = TargetContext.TRANSACTION_CANONICAL
    source_system: str = Field(default="FILE_UPLOAD", pattern=r"^[A-Za-z0-9_.:-]{1,80}$")


class ImportRead(BaseModel):
    id: UUID
    company_id: UUID
    source_type: SourceType
    target_context: TargetContext
    source_system: str
    original_filename: str
    file_sha256: str
    status: str
    version: int
    mapping_version: int
    preview_digest: str | None
    preview_expires_at: datetime | None
    created_at: datetime


class MappingInput(Command):
    sheet_index: int = Field(ge=0, lt=5)
    column_index: int = Field(ge=0, lt=40)
    canonical_field_code: str | None = Field(default=None, max_length=50)


class MappingUpdate(Command):
    expected_version: int = Field(ge=1)
    mappings: list[MappingInput] = Field(min_length=1, max_length=200)


class PreviewCommand(Command):
    expected_version: int = Field(ge=1)


class ConfirmCommand(PreviewCommand):
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]


class MappingRead(BaseModel):
    sheet_index: int
    column_index: int
    canonical_field_code: str | None
    status: str


class ColumnRead(BaseModel):
    sheet_index: int
    sheet_name: str
    column_index: int
    source_header: str
    mapping: MappingRead


class FieldRead(BaseModel):
    code: str
    label: str
    kind: str
    required: bool


class ColumnsRead(BaseModel):
    columns: list[ColumnRead]
    fields: list[FieldRead]


class ValidationErrorRead(BaseModel):
    sheet_index: int
    row_number: int
    column_index: int
    error_code: str
    severity: str
    message: str
    canonical_field_code: str | None


class PreviewRow(BaseModel):
    sheet_index: int
    row_number: int
    source_id: str
    values: list[tuple[str, str]]


class PreviewRead(BaseModel):
    import_id: UUID
    preview_digest: str
    version: int
    expires_at: datetime
    valid: bool
    row_count: int
    errors: list[ValidationErrorRead]
    rows: list[PreviewRow]


class ReceiptRead(BaseModel):
    id: UUID
    company_id: UUID
    import_id: UUID
    source_digest: str
    transaction_count: int
    evidence_count: int
    counterparty_count: int
    status: str
    created_at: datetime
