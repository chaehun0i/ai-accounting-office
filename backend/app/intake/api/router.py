from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.composition import Services
from app.contracts.access_errors import InvalidInput
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf, principal, services
from app.identity.users.domain.entities import Principal
from app.intake.api.schemas import (
    ColumnRead,
    ColumnsRead,
    ConfirmCommand,
    FieldRead,
    ImportRead,
    MappingUpdate,
    PreviewCommand,
    PreviewRead,
    ReceiptRead,
    UploadCommand,
    ValidationErrorRead,
)
from app.intake.api.upload import receive_upload
from app.intake.application.service import IntakeService
from app.intake.domain.canonical_fields import SCHEMAS, Mapping, SourceType, TargetContext

router = APIRouter(prefix="/imports", tags=["자료 가져오기"])
Actor = Annotated[Principal, Depends(principal)]
Container = Annotated[Services, Depends(services)]
CompanyScope = Annotated[UUID, Header(alias="X-Company-ID")]


def intake(container: Container) -> IntakeService:
    if container.intake is None:
        raise DatabaseUnavailable()
    return container.intake


Service = Annotated[IntakeService, Depends(intake)]


@router.post(
    "",
    response_model=ImportRead,
    status_code=201,
    dependencies=[Depends(csrf)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file", "source_type"],
                        "additionalProperties": False,
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                            "source_type": {
                                "type": "string",
                                "enum": [s.value for s in SourceType],
                            },
                            "target_context": {
                                "type": "string",
                                "enum": [s.value for s in TargetContext],
                                "default": "TRANSACTION_CANONICAL",
                            },
                            "source_system": {
                                "type": "string",
                                "default": "FILE_UPLOAD",
                                "pattern": "^[A-Za-z0-9_.:-]{1,80}$",
                            },
                        },
                    },
                }
            },
        }
    },
)
async def upload(
    request: Request, actor: Actor, company_id: CompanyScope, service: Service
) -> ImportRead:
    file = await receive_upload(request)
    try:
        command = UploadCommand.model_validate(file.fields)
    except ValidationError:
        raise InvalidInput() from None
    if command.source_type == SourceType.ONBOARDING_TEMPLATE:
        raise InvalidInput()
    value = await run_in_threadpool(
        service.upload,
        actor,
        company_id,
        source=command.source_type,
        target=command.target_context,
        source_system=command.source_system,
        filename=file.filename,
        content=file.content,
        content_type=file.content_type,
    )
    return ImportRead.model_validate(asdict(value))


@router.get("/{identifier}", response_model=ImportRead)
def read(identifier: UUID, actor: Actor, company_id: CompanyScope, service: Service) -> ImportRead:
    return ImportRead.model_validate(asdict(service.get(actor, company_id, identifier)))


@router.get("/{identifier}/columns", response_model=ColumnsRead)
def columns(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> ColumnsRead:
    value = service.get(actor, company_id, identifier)
    return ColumnsRead(
        columns=[
            ColumnRead.model_validate(asdict(c))
            for c in service.columns(actor, company_id, identifier)
        ],
        fields=[FieldRead.model_validate(asdict(f)) for f in SCHEMAS[value.source_type]],
    )


@router.put("/{identifier}/mapping", response_model=ImportRead, dependencies=[Depends(csrf)])
def mapping(
    identifier: UUID,
    payload: MappingUpdate,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> ImportRead:
    mappings = [
        Mapping(m.sheet_index, m.column_index, m.canonical_field_code, "USER_CONFIRMED")
        for m in payload.mappings
    ]
    return ImportRead.model_validate(
        asdict(service.mapping(actor, company_id, identifier, payload.expected_version, mappings))
    )


@router.post("/{identifier}/preview", response_model=PreviewRead, dependencies=[Depends(csrf)])
def preview(
    identifier: UUID,
    payload: PreviewCommand,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
) -> PreviewRead:
    return PreviewRead.model_validate(
        asdict(service.preview(actor, company_id, identifier, payload.expected_version))
    )


@router.post("/{identifier}/confirm", response_model=ReceiptRead, dependencies=[Depends(csrf)])
def confirm(
    identifier: UUID,
    payload: ConfirmCommand,
    actor: Actor,
    company_id: CompanyScope,
    service: Service,
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)],
) -> ReceiptRead:
    return ReceiptRead.model_validate(
        asdict(
            service.confirm(
                actor, company_id, identifier, idempotency_key=key, **payload.model_dump()
            )
        )
    )


@router.get("/{identifier}/errors", response_model=list[ValidationErrorRead])
def errors(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> list[ValidationErrorRead]:
    return [
        ValidationErrorRead.model_validate(asdict(e))
        for e in service.errors(actor, company_id, identifier)
    ]


@router.get("/{identifier}/receipt", response_model=ReceiptRead)
def receipt(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Service
) -> ReceiptRead:
    return ReceiptRead.model_validate(asdict(service.receipt(actor, company_id, identifier)))
