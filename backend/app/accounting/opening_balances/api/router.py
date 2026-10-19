"""기초잔액 전표와 Cutover 사전 대조 API를 한 모듈에서 제공합니다."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.journals.api.router import read
from app.accounting.journals.api.schemas import JournalRead
from app.accounting.opening_balances.application.ar_ap_preview import ArApPreview
from app.contracts.errors import DatabaseUnavailable
from app.identity.auth.api.dependencies import csrf

router = APIRouter(tags=["기초잔액 Cutover"])
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


class OpeningCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class ArApPreviewIssueRead(BaseModel):
    code: str
    section: str
    row_key: str
    message: str


class ArApPreviewTotalRead(BaseModel):
    role: str
    account_code: str
    counterparty_code: str
    opening_amount: Decimal
    item_amount: Decimal


class ArApPreviewRead(BaseModel):
    session_version: int
    source_digest: str
    as_of_date: date | None
    ready: bool
    issues: list[ArApPreviewIssueRead]
    totals: list[ArApPreviewTotalRead]


@router.get("/opening-balances/ar-ap-preview", response_model=ArApPreviewRead)
def opening_ar_ap_preview(
    expected_version: int,
    actor: Actor,
    company_id: CompanyScope,
    container: Container,
) -> ArApPreviewRead:
    if container.opening_balances is None:
        raise DatabaseUnavailable()
    result: ArApPreview = container.opening_balances.ar_ap_preview(
        actor, company_id, expected_version
    )
    return ArApPreviewRead.model_validate(asdict(result))


@router.post(
    "/opening-balances/imports",
    response_model=JournalRead,
    status_code=201,
    dependencies=[Depends(csrf)],
)
def opening(
    payload: OpeningCommand, actor: Actor, company_id: CompanyScope, container: Container, key: Key
) -> JournalRead:
    if container.opening_balances is None:
        raise DatabaseUnavailable()
    return read(container.opening_balances.create(actor, company_id, payload.expected_version, key))
