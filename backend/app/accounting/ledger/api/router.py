from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.accounting.api.router import Actor, CompanyScope, Container
from app.accounting.ledger.application.service import AccountingReports
from app.contracts.errors import DatabaseUnavailable

router = APIRouter(tags=["총계정원장·시산표"])


def reports(container: Container) -> AccountingReports:
    if container.accounting_reports is None:
        raise DatabaseUnavailable()
    return container.accounting_reports


Reports = Annotated[AccountingReports, Depends(reports)]


class LedgerRead(BaseModel):
    journal_id: UUID
    line_id: UUID
    entry_date: date
    journal_no: str
    account_id: UUID
    account_code: str
    account_name: str
    normal_balance: str
    counterparty_id: UUID | None
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    source_transaction_id: UUID | None
    import_id: UUID | None
    running_balance: Decimal


class TrialRead(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    opening_debit: Decimal
    opening_credit: Decimal
    period_debit: Decimal
    period_credit: Decimal
    ending_debit: Decimal
    ending_credit: Decimal
    normal_balance: str
    ending_balance: Decimal


@router.get("/ledger", response_model=list[LedgerRead])
def read_ledger(
    account_id: UUID,
    date_from: date,
    date_to: date,
    actor: Actor,
    company_id: CompanyScope,
    service: Reports,
) -> list[LedgerRead]:
    return [
        LedgerRead(**asdict(r))
        for r in service.ledger(actor, company_id, account_id, date_from, date_to)
    ]


@router.get("/trial-balance", response_model=list[TrialRead])
def read_trial(
    period_id: UUID, actor: Actor, company_id: CompanyScope, service: Reports
) -> list[TrialRead]:
    return [TrialRead(**asdict(r)) for r in service.trial(actor, company_id, period_id)]
