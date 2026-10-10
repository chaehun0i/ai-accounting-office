from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueUpdate(StrictModel):
    field_code: str = Field(max_length=100)
    row_key: str = Field(default="singleton", min_length=1, max_length=260)
    value: str | StrictBool | StrictInt


class ValuesUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    values: list[ValueUpdate] = Field(min_length=1, max_length=500)


class VersionCommand(StrictModel):
    expected_version: int = Field(ge=1)


class ApplyCommand(VersionCommand):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    choices: dict[str, Literal["KEEP_CURRENT", "APPLY_IMPORT"]] = Field(
        default_factory=dict, max_length=1000
    )


class CellRead(BaseModel):
    field_code: str
    row_key: str
    value: str | bool | Decimal | date
    source_type: str
    status: str
    version: int


class FieldRead(BaseModel):
    field_code: str
    section_code: str
    label: str
    data_type: str
    input_mode: str
    required_rule_code: str
    enum_source_code: str | None
    derived_handler_key: str | None
    display_order: int
    active: bool


class SectionRead(BaseModel):
    code: str
    label: str
    complete: int
    total: int
    status: str


class WorkspaceRead(BaseModel):
    id: UUID
    company_id: UUID
    status: str
    version: int
    cells: list[CellRead]
    fields: list[FieldRead]
    sections: list[SectionRead]
    enums: dict[str, tuple[str, ...]]
    row_keys: dict[str, tuple[str, ...]]


class IssueRead(BaseModel):
    field_code: str | None
    row_key: str
    validation_code: str
    severity: str
    message: str


class ValidationRead(BaseModel):
    workspace: WorkspaceRead
    issues: list[IssueRead]


class ImportRead(BaseModel):
    import_id: UUID
    session_id: UUID
    status: str
    template_code: str
    template_version: str


class MergeItemRead(BaseModel):
    incoming: CellRead
    current: CellRead | None
    classification: str


class PreviewRead(BaseModel):
    import_id: UUID
    session_version: int
    digest: str
    expires_at: datetime
    items: list[MergeItemRead]
    errors: list[IssueRead]
    counts: dict[str, int]


class ReceiptRead(BaseModel):
    id: UUID
    session_id: UUID
    import_id: UUID | None
    fingerprint: str
    new_count: int
    changed_count: int
    unchanged_count: int
    conflict_count: int
    error_count: int
    created_at: datetime
