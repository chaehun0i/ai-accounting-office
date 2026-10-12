"""기존 인증·회사·CSRF 경계를 통과한 금융 대사 명령입니다."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.accounting.api.router import Actor, CompanyScope, Container
from app.contracts.errors import DatabaseUnavailable
from app.finance.banking.api.schemas import (
    AccountCreate,
    Confirm,
    ItemCreate,
    MatchCreate,
    ResolveItem,
    SourceImport,
    StatementImport,
    Unmatch,
)
from app.finance.banking.application.service import BankingService
from app.finance.banking.domain.entities import (
    CardSummary,
    FinancialAccount,
    FinancialSource,
    Match,
    ReconciliationItem,
    ReconciliationLine,
    Statement,
    StatementSummary,
)
from app.finance.reconciliation.application.bank_service import BankReconciliationService
from app.finance.reconciliation.domain.rules import Candidate
from app.finance.settlements.api.router import Key
from app.identity.auth.api.dependencies import csrf

router = APIRouter(tags=["은행·카드 대사"])


def banking(container: Container) -> BankingService:
    if container.banking is None:
        raise DatabaseUnavailable()
    return container.banking


def reconciliation(container: Container) -> BankReconciliationService:
    if container.bank_reconciliation is None:
        raise DatabaseUnavailable()
    return container.bank_reconciliation


Banking = Annotated[BankingService, Depends(banking)]
Reconciliation = Annotated[BankReconciliationService, Depends(reconciliation)]


@router.get("/bank-accounts")
def bank_accounts(
    actor: Actor, company_id: CompanyScope, service: Banking
) -> list[FinancialAccount]:
    return service.accounts(actor, company_id, "BANK")


@router.post("/bank-accounts", status_code=201, dependencies=[Depends(csrf)])
def create_bank(
    payload: AccountCreate, actor: Actor, company_id: CompanyScope, service: Banking
) -> FinancialAccount:
    return service.create_account(
        actor,
        company_id,
        "BANK",
        payload.institution_code,
        payload.alias,
        payload.control_account_id,
        payload.usage_type,
    )


@router.get("/card-accounts")
def card_accounts(
    actor: Actor, company_id: CompanyScope, service: Banking
) -> list[FinancialAccount]:
    return service.accounts(actor, company_id, "CARD")


@router.post("/card-accounts", status_code=201, dependencies=[Depends(csrf)])
def create_card(
    payload: AccountCreate, actor: Actor, company_id: CompanyScope, service: Banking
) -> FinancialAccount:
    return service.create_account(
        actor,
        company_id,
        "CARD",
        payload.institution_code,
        payload.alias,
        payload.control_account_id,
        payload.usage_type,
    )


@router.get("/bank-statements")
def statements(actor: Actor, company_id: CompanyScope, service: Banking) -> list[Statement]:
    return service.statements(actor, company_id)


@router.post("/bank-statements/imports", dependencies=[Depends(csrf)])
def import_statement(
    payload: StatementImport, key: Key, actor: Actor, company_id: CompanyScope, service: Banking
) -> Statement | list[FinancialSource]:
    return service.import_source(
        actor,
        company_id,
        "BANK",
        payload.account_id,
        payload.import_id,
        payload.receipt_id,
        payload.source_digest,
        payload.confirmed_version,
        key,
        payload.statement_start,
        payload.statement_end,
        payload.opening_balance,
        payload.closing_balance,
    )


@router.post("/card-transactions/imports", dependencies=[Depends(csrf)])
def import_cards(
    payload: SourceImport, key: Key, actor: Actor, company_id: CompanyScope, service: Banking
) -> Statement | list[FinancialSource]:
    return service.import_source(
        actor,
        company_id,
        "CARD",
        payload.account_id,
        payload.import_id,
        payload.receipt_id,
        payload.source_digest,
        payload.confirmed_version,
        key,
    )


@router.get("/bank-statements/{identifier}")
def statement(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Banking
) -> Statement:
    return service.statement(actor, company_id, identifier)


@router.get("/bank-statements/{identifier}/transactions")
def statement_sources(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Banking
) -> list[FinancialSource]:
    return service.sources(actor, company_id, "BANK", statement=identifier)


@router.get("/card-transactions")
def card_sources(
    actor: Actor, company_id: CompanyScope, service: Banking, account_id: UUID | None = None
) -> list[FinancialSource]:
    return service.sources(actor, company_id, "CARD", account=account_id)


@router.post("/bank-statements/{identifier}/match-candidates", dependencies=[Depends(csrf)])
def statement_candidates(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Reconciliation
) -> list[Candidate]:
    return service.statement_candidates(actor, company_id, identifier)


@router.post("/card-transactions/{identifier}/match-candidates", dependencies=[Depends(csrf)])
def card_candidates(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Reconciliation
) -> list[Candidate]:
    return service.candidates(actor, company_id, "CARD", identifier)


@router.get("/reconciliations")
def matches(actor: Actor, company_id: CompanyScope, service: Reconciliation) -> list[Match]:
    return service.matches(actor, company_id)


@router.get("/reconciliations/{identifier}")
def match(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Reconciliation
) -> Match:
    return service.get(actor, company_id, identifier)


@router.post("/reconciliations", status_code=201, dependencies=[Depends(csrf)])
def create_match(
    payload: MatchCreate, key: Key, actor: Actor, company_id: CompanyScope, service: Reconciliation
) -> Match:
    return service.create(
        actor,
        company_id,
        tuple(ReconciliationLine(**line.model_dump()) for line in payload.lines),
        key,
    )


@router.post("/reconciliations/{identifier}/confirm", dependencies=[Depends(csrf)])
def confirm(
    identifier: UUID,
    payload: Confirm,
    key: Key,
    actor: Actor,
    company_id: CompanyScope,
    service: Reconciliation,
) -> Match:
    return service.command(actor, company_id, identifier, payload.expected_version, key)


@router.post("/reconciliations/{identifier}/unmatch", dependencies=[Depends(csrf)])
def unmatch(
    identifier: UUID,
    payload: Unmatch,
    key: Key,
    actor: Actor,
    company_id: CompanyScope,
    service: Reconciliation,
) -> Match:
    return service.command(
        actor,
        company_id,
        identifier,
        payload.expected_version,
        key,
        unmatch=True,
        reason=payload.reason,
    )


@router.get("/bank-statements/{identifier}/summary")
def summary(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Reconciliation
) -> StatementSummary:
    return service.summary(actor, company_id, identifier)


@router.get("/reconciliation/summary")
def period_summary(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Reconciliation
) -> list[StatementSummary]:
    return service.period_summary(actor, company_id, period_id)


@router.get("/bank-statements/{identifier}/items")
def items(
    identifier: UUID, actor: Actor, company_id: CompanyScope, service: Reconciliation
) -> list[ReconciliationItem]:
    return service.items(actor, company_id, identifier)


@router.post("/bank-statements/{identifier}/items", status_code=201, dependencies=[Depends(csrf)])
def create_item(
    identifier: UUID,
    payload: ItemCreate,
    key: Key,
    actor: Actor,
    company_id: CompanyScope,
    service: Reconciliation,
) -> ReconciliationItem:
    return service.item(
        actor, company_id, identifier, payload.reason_code, payload.amount, payload.description, key
    )


@router.post("/bank-statements/{identifier}/close", dependencies=[Depends(csrf)])
def close(
    identifier: UUID,
    payload: Confirm,
    key: Key,
    actor: Actor,
    company_id: CompanyScope,
    service: Reconciliation,
) -> StatementSummary:
    return service.close(actor, company_id, identifier, payload.expected_version, key)


@router.post("/bank-statements/{identifier}/items/{item_id}/resolve", dependencies=[Depends(csrf)])
def resolve_item(
    identifier: UUID,
    item_id: UUID,
    payload: ResolveItem,
    key: Key,
    actor: Actor,
    company_id: CompanyScope,
    service: Reconciliation,
) -> ReconciliationItem:
    return service.resolve_item(
        actor,
        company_id,
        identifier,
        item_id,
        payload.expected_version,
        payload.resolution_note,
        key,
    )


@router.get("/card-accounts/{identifier}/summary")
def card_summary(
    identifier: UUID, as_of: date, actor: Actor, company_id: CompanyScope, service: Reconciliation
) -> CardSummary:
    return service.card_summary(actor, company_id, identifier, as_of)
