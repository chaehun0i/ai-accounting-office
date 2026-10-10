from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from starlette.concurrency import run_in_threadpool

from app.contracts.access_errors import InvalidInput
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf
from app.intake.api.router import Actor, CompanyScope, Container
from app.intake.api.upload import receive_upload
from app.intake.infrastructure.parser import XLSX_MIME
from app.onboarding.api.schemas import (
    ApplyCommand,
    ImportRead,
    PreviewRead,
    ReceiptRead,
    ValidationRead,
    ValuesUpdate,
    VersionCommand,
    WorkspaceRead,
)
from app.onboarding.application.complete import CompleteOnboarding
from app.onboarding.application.merge import OnboardingImportService
from app.onboarding.application.service import OnboardingService
from app.onboarding.domain.catalog import CATALOG, ENUMS, KEYS, SECTIONS
from app.onboarding.domain.entities import Workspace
from app.onboarding.domain.validation import progress
from app.onboarding.infrastructure.template import generate_template

router = APIRouter(prefix="/onboarding", tags=["회계 시작 준비"])


def workspace_read(value: Workspace) -> WorkspaceRead:
    return WorkspaceRead.model_validate(
        {
            **asdict(value),
            "fields": [asdict(f) for f in CATALOG],
            "enums": ENUMS,
            "row_keys": KEYS,
            "sections": [
                {
                    "code": code,
                    "label": label,
                    "complete": progress(value.cells, code)[0],
                    "total": progress(value.cells, code)[1],
                    "status": progress(value.cells, code)[2],
                }
                for code, label in SECTIONS.items()
            ],
        }
    )


def require_service(container: Container) -> tuple[OnboardingService, OnboardingImportService]:
    if container.onboarding is None or container.onboarding_imports is None:
        raise DatabaseUnavailable()
    return container.onboarding, container.onboarding_imports


@router.get("", response_model=WorkspaceRead)
def get(actor: Actor, company_id: CompanyScope, container: Container) -> WorkspaceRead:
    service, _ = require_service(container)
    return workspace_read(service.get(actor, company_id))


@router.patch("/values", response_model=WorkspaceRead, dependencies=[Depends(csrf)])
def save(
    payload: ValuesUpdate, actor: Actor, company_id: CompanyScope, container: Container
) -> WorkspaceRead:
    service, _ = require_service(container)
    return workspace_read(
        service.save(
            actor,
            company_id,
            payload.expected_version,
            [(v.field_code, v.row_key, v.value) for v in payload.values],
        )
    )


@router.post("/validate", response_model=ValidationRead, dependencies=[Depends(csrf)])
def validate(
    payload: VersionCommand, actor: Actor, company_id: CompanyScope, container: Container
) -> ValidationRead:
    service, _ = require_service(container)
    value, issues = service.validate(actor, company_id, payload.expected_version)
    return ValidationRead.model_validate(
        {"workspace": workspace_read(value), "issues": [asdict(i) for i in issues]}
    )


@router.get("/templates/current")
def template(actor: Actor, company_id: CompanyScope, container: Container) -> Response:
    service, _ = require_service(container)
    service.get(actor, company_id)
    return Response(
        generate_template(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="accounting-onboarding-v1.xlsx"'},
    )


@router.post(
    "/imports",
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
                        "required": ["file"],
                        "additionalProperties": False,
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def upload(
    request: Request, actor: Actor, company_id: CompanyScope, container: Container
) -> ImportRead:
    _, service = require_service(container)
    file = await receive_upload(request)
    if file.fields:
        raise InvalidInput()
    value = await run_in_threadpool(
        service.upload, actor, company_id, file.filename, file.content, file.content_type
    )
    return ImportRead.model_validate(asdict(value))


@router.get("/imports/{identifier}", response_model=ImportRead)
def get_import(
    identifier: UUID, actor: Actor, company_id: CompanyScope, container: Container
) -> ImportRead:
    _, service = require_service(container)
    return ImportRead.model_validate(asdict(service.get(actor, company_id, identifier)))


@router.post(
    "/imports/{identifier}/preview", response_model=PreviewRead, dependencies=[Depends(csrf)]
)
def preview(
    identifier: UUID,
    payload: VersionCommand,
    actor: Actor,
    company_id: CompanyScope,
    container: Container,
) -> PreviewRead:
    _, service = require_service(container)
    value = service.preview(actor, company_id, identifier, payload.expected_version)
    counts = {
        code: sum(i.classification == code for i in value.items)
        for code in ("APPLY", "UNCHANGED", "CONFLICT")
    }
    counts["ERROR"] = len(value.errors)
    return PreviewRead.model_validate({**asdict(value), "counts": counts})


@router.post(
    "/imports/{identifier}/apply", response_model=ReceiptRead, dependencies=[Depends(csrf)]
)
def apply(
    identifier: UUID,
    payload: ApplyCommand,
    actor: Actor,
    company_id: CompanyScope,
    container: Container,
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)],
) -> ReceiptRead:
    _, service = require_service(container)
    return ReceiptRead.model_validate(
        asdict(
            service.apply(
                actor,
                company_id,
                identifier,
                payload.expected_version,
                payload.preview_digest,
                dict(payload.choices),
                key,
            )
        )
    )


@router.post("/complete", response_model=ReceiptRead, dependencies=[Depends(csrf)])
def complete(
    payload: VersionCommand,
    actor: Actor,
    company_id: CompanyScope,
    container: Container,
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)],
) -> ReceiptRead:
    service, _ = require_service(container)
    return ReceiptRead.model_validate(
        asdict(
            CompleteOnboarding(service).complete(actor, company_id, payload.expected_version, key)
        )
    )
