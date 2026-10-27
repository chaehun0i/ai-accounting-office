"""POSTED 장부의 현금 범위를 명시적 설정으로 사전 점검합니다."""

import re
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.closing.application.service import ClosingService
from app.closing.domain.errors import ClosingRunStale
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.cash_flow.direct_events import direct_events
from app.reporting.cash_flow.entities import (
    CashAllocation,
    CashClassification,
    CashEvent,
    CashPreflight,
    CashPreflightIssue,
    CashScope,
)
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.financial_statements.domain.rules import ReportSourceStale

ZERO = Decimal("0")
MAX_ALLOCATION = Decimal("9999999999999999.9999")
ACTIVITIES = ("OPERATING", "INVESTING", "FINANCING", "EXCHANGE_EFFECT")


def covers_period(start: date, end: date | None, period_start: date, period_end: date) -> bool:
    return start <= period_start and (end is None or end >= period_end)


def _valid_amount(amount: Decimal, *, allow_zero: bool = False) -> bool:
    exponent = amount.as_tuple().exponent
    return (
        amount.is_finite()
        and (amount >= ZERO if allow_zero else amount > ZERO)
        and isinstance(exponent, int)
        and exponent >= -4
        and amount <= MAX_ALLOCATION
    )


class CashFlowService:
    def __init__(self, factory: Callable[[], CashFlowUnitOfWork]) -> None:
        self.factory = factory

    def scopes(self, actor: Principal, company: UUID) -> tuple[CashScope, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return uow.cash_flow.scopes(company)

    def classifications(self, actor: Principal, company: UUID) -> tuple[CashClassification, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return uow.cash_flow.classifications(company)

    def allocation_history(
        self, actor: Principal, company: UUID, journal_id: UUID
    ) -> tuple[CashAllocation, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            if uow.journals.get(company, journal_id) is None:
                raise ResourceNotFound()
            return uow.cash_flow.allocation_history(company, journal_id)

    def map_cash(
        self,
        actor: Principal,
        company: UUID,
        account_id: UUID,
        scope_type: str,
        effective_from: date,
    ) -> CashScope:
        if scope_type not in ("CASH", "CASH_EQUIVALENT"):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            account = uow.accounts.get(company_id=company, resource_id=account_id)
            if account is None:
                raise ResourceNotFound()
            if (
                account.account_type != "ASSET"
                or account.is_contra
                or not account.posting_allowed
                or account.status != "ACTIVE"
            ):
                raise InvalidInput()
            if any(row.account_id == account_id for row in uow.cash_flow.classifications(company)):
                raise StateConflict()
            old = next(
                (row for row in uow.cash_flow.scopes(company) if row.account_id == account_id), None
            )
            if old is not None:
                if old.scope_type != scope_type or old.effective_from != effective_from:
                    raise StateConflict()
                return old
            return uow.cash_flow.add_scope(
                company, account_id, scope_type, effective_from, actor.user_id, uow.now()
            )

    def map_activity(
        self,
        actor: Principal,
        company: UUID,
        account_id: UUID,
        activity_type: str,
        line_code: str,
        effective_from: date,
    ) -> CashClassification:
        if activity_type not in ACTIVITIES or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", line_code):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            account = uow.accounts.get(company_id=company, resource_id=account_id)
            if account is None:
                raise ResourceNotFound()
            if not account.posting_allowed or account.status != "ACTIVE":
                raise InvalidInput()
            if any(row.account_id == account_id for row in uow.cash_flow.scopes(company)):
                raise StateConflict()
            old = next(
                (
                    row
                    for row in uow.cash_flow.classifications(company)
                    if row.account_id == account_id
                ),
                None,
            )
            if old is not None:
                if (
                    old.activity_type != activity_type
                    or old.line_code != line_code
                    or old.effective_from != effective_from
                ):
                    raise StateConflict()
                return old
            return uow.cash_flow.add_classification(
                company,
                account_id,
                activity_type,
                line_code,
                effective_from,
                actor.user_id,
                uow.now(),
            )

    def preflight(self, actor: Principal, company: UUID, period_id: UUID) -> CashPreflight:
        return self._analyze(actor, company, period_id)[0]

    def events(self, actor: Principal, company: UUID, period_id: UUID) -> tuple[CashEvent, ...]:
        preflight, events = self._analyze(actor, company, period_id)
        if not preflight.ready:
            raise StateConflict()
        return events

    def allocate(
        self,
        actor: Principal,
        company: UUID,
        journal_id: UUID,
        cash_line_id: UUID,
        counterpart_line_id: UUID,
        evidence_id: UUID,
        amount: Decimal,
    ) -> CashAllocation:
        if not _valid_amount(amount):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            journal = uow.journals.get(company, journal_id)
            if journal is None:
                raise ResourceNotFound()
            if journal.status != "POSTED" or journal.source_type == "OPENING":
                raise StateConflict()
            try:
                period, _, _, _, facts = ClosingService.closed_adjusted_source(
                    uow, company, journal.accounting_period_id
                )
            except ClosingRunStale:
                raise ReportSourceStale() from None
            locked_journal = uow.cash_flow.lock_journal(company, journal_id)
            if locked_journal is None or locked_journal.status != "POSTED":
                raise StateConflict()
            if not (period.start_date <= locked_journal.entry_date <= period.end_date):
                raise StateConflict()
            journal_facts = [fact for fact in facts if fact.journal_id == journal_id]
            cash_accounts = {row.account_id for row in uow.cash_flow.scopes(company)}
            cash_fact = next((f for f in journal_facts if f.line_id == cash_line_id), None)
            other_fact = next((f for f in journal_facts if f.line_id == counterpart_line_id), None)
            if (
                cash_fact is None
                or other_fact is None
                or cash_fact.account_id not in cash_accounts
                or other_fact.account_id in cash_accounts
                or (cash_fact.debit_amount - cash_fact.credit_amount)
                * (other_fact.debit_amount - other_fact.credit_amount)
                >= ZERO
                or not uow.cash_flow.evidence_linked(company, journal_id, evidence_id)
            ):
                raise InvalidInput()
            if (
                len([f for f in journal_facts if f.account_id in cash_accounts]) == 1
                and len([f for f in journal_facts if f.account_id not in cash_accounts]) == 1
            ):
                raise StateConflict()  # ordinary two-line journals are derived without allocation
            existing = uow.cash_flow.allocations(company, journal_id)
            history = uow.cash_flow.allocation_history(company, journal_id)
            old = next(
                (
                    a
                    for a in existing
                    if a.cash_line_id == cash_line_id
                    and a.counterpart_line_id == counterpart_line_id
                ),
                None,
            )
            if old is not None:
                if old.amount != amount or old.evidence_id != evidence_id:
                    raise StateConflict()
                return old
            if any(
                a.cash_line_id == cash_line_id and a.counterpart_line_id == counterpart_line_id
                for a in history
            ):
                raise StateConflict()  # revive a retracted pair by revising its latest row
            if sum(
                (a.amount for a in existing if a.cash_line_id == cash_line_id), ZERO
            ) + amount > abs(cash_fact.debit_amount - cash_fact.credit_amount) or sum(
                (a.amount for a in existing if a.counterpart_line_id == counterpart_line_id), ZERO
            ) + amount > abs(other_fact.debit_amount - other_fact.credit_amount):
                raise InvalidInput()
            return uow.cash_flow.add_allocation(
                company,
                journal_id,
                cash_line_id,
                counterpart_line_id,
                evidence_id,
                amount,
                actor.user_id,
                uow.now(),
            )

    def revise_allocation(
        self,
        actor: Principal,
        company: UUID,
        allocation_id: UUID,
        amount: Decimal,
        evidence_id: UUID,
    ) -> CashAllocation:
        """Append a revision; zero retracts an erroneous pair without deleting its audit trail."""
        if not _valid_amount(amount, allow_zero=True):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            old = uow.cash_flow.allocation(company, allocation_id)
            if old is None:
                raise ResourceNotFound()
            journal = uow.journals.get(company, old.journal_id)
            if journal is None:
                raise ResourceNotFound()
            if journal.status != "POSTED" or journal.source_type == "OPENING":
                raise StateConflict()
            try:
                _, _, _, _, facts = ClosingService.closed_adjusted_source(
                    uow, company, journal.accounting_period_id
                )
            except ClosingRunStale:
                raise ReportSourceStale() from None
            locked_journal = uow.cash_flow.lock_journal(company, old.journal_id)
            if locked_journal is None or locked_journal.status != "POSTED":
                raise StateConflict()
            history = uow.cash_flow.allocation_history(company, old.journal_id)
            pair = [
                row
                for row in history
                if row.cash_line_id == old.cash_line_id
                and row.counterpart_line_id == old.counterpart_line_id
            ]
            if (
                pair[-1].replaces_id == old.id
                and pair[-1].amount == amount
                and pair[-1].evidence_id == evidence_id
            ):
                return pair[-1]  # retry of the same correction
            if pair[-1].id != old.id:
                raise StateConflict()
            if old.amount == amount and old.evidence_id == evidence_id:
                return old
            if not uow.cash_flow.evidence_linked(company, old.journal_id, evidence_id):
                raise InvalidInput()
            cash_fact = next((f for f in facts if f.line_id == old.cash_line_id), None)
            other_fact = next((f for f in facts if f.line_id == old.counterpart_line_id), None)
            if cash_fact is None or other_fact is None:
                raise StateConflict()
            current = [
                row
                for row in uow.cash_flow.allocations(company, old.journal_id)
                if row.id != old.id
            ]
            if sum(
                (a.amount for a in current if a.cash_line_id == old.cash_line_id), ZERO
            ) + amount > abs(cash_fact.debit_amount - cash_fact.credit_amount) or sum(
                (a.amount for a in current if a.counterpart_line_id == old.counterpart_line_id),
                ZERO,
            ) + amount > abs(other_fact.debit_amount - other_fact.credit_amount):
                raise InvalidInput()
            return uow.cash_flow.add_allocation(
                company,
                old.journal_id,
                old.cash_line_id,
                old.counterpart_line_id,
                evidence_id,
                amount,
                actor.user_id,
                uow.now(),
                old.version + 1,
                old.id,
            )

    def _analyze(
        self, actor: Principal, company: UUID, period_id: UUID
    ) -> tuple[CashPreflight, tuple[CashEvent, ...]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            try:
                period, _, source_digest, _, facts = ClosingService.closed_adjusted_source(
                    uow, company, period_id
                )
            except ClosingRunStale:
                raise ReportSourceStale() from None
            scopes = uow.cash_flow.scopes(company)
            classes = uow.cash_flow.classifications(company)
            allocations = uow.cash_flow.allocations(company)
            period_journal_ids = {
                fact.journal_id
                for fact in facts
                if period.start_date <= fact.entry_date and fact.source_type != "OPENING"
            }
            mapping_digest = digest(
                (
                    [
                        (
                            str(r.account_id),
                            r.scope_type,
                            r.effective_from.isoformat(),
                            r.effective_to.isoformat() if r.effective_to else None,
                            r.version,
                        )
                        for r in scopes
                    ],
                    [
                        (
                            str(r.account_id),
                            r.activity_type,
                            r.line_code,
                            r.effective_from.isoformat(),
                            r.effective_to.isoformat() if r.effective_to else None,
                            r.version,
                        )
                        for r in classes
                    ],
                    [
                        (
                            str(a.id),
                            a.version,
                            str(a.journal_id),
                            str(a.cash_line_id),
                            str(a.counterpart_line_id),
                            str(a.evidence_id),
                            str(a.amount),
                        )
                        for a in allocations
                        if a.journal_id in period_journal_ids
                    ],
                )
            )
            issues: list[CashPreflightIssue] = []
            if not scopes:
                issues.append(CashPreflightIssue("CASH_SCOPE_MISSING"))
            cash_accounts = {row.account_id for row in scopes}
            for row in scopes:
                if not covers_period(
                    row.effective_from, row.effective_to, period.start_date, period.end_date
                ):
                    issues.append(CashPreflightIssue("CASH_SCOPE_NOT_FULL_PERIOD"))
            classes_by_account = {row.account_id: row for row in classes}
            opening = sum(
                (
                    f.debit_amount - f.credit_amount
                    for f in facts
                    if f.account_id in cash_accounts
                    and (f.entry_date < period.start_date or f.source_type == "OPENING")
                ),
                ZERO,
            )
            closing = sum(
                (f.debit_amount - f.credit_amount for f in facts if f.account_id in cash_accounts),
                ZERO,
            )
            by_journal = defaultdict(list)
            for fact in facts:
                if period.start_date <= fact.entry_date and fact.source_type != "OPENING":
                    by_journal[fact.journal_id].append(fact)
            amounts = {activity: ZERO for activity in ACTIVITIES}
            classified = 0
            all_events: list[CashEvent] = []
            for journal_id, journal_facts in by_journal.items():
                cash = [f for f in journal_facts if f.account_id in cash_accounts]
                if not cash:
                    continue
                journal_events, error = direct_events(
                    journal_facts,
                    cash_accounts,
                    classes_by_account,
                    tuple(a for a in allocations if a.journal_id == journal_id),
                )
                if error is not None:
                    issues.append(CashPreflightIssue(error, journal_id))
                    continue
                for event in journal_events:
                    amounts[event.activity_type] += event.cash_inflow - event.cash_outflow
                all_events.extend(journal_events)
                if journal_events:
                    classified += 1
            net_movement = closing - opening
            if not issues and sum(amounts.values(), ZERO) != net_movement:
                issues.append(CashPreflightIssue("CASH_FLOW_RECONCILIATION_MISMATCH"))
            preflight = CashPreflight(
                period_id=period_id,
                close_version=period.close_version,
                source_digest=source_digest,
                mapping_digest=mapping_digest,
                opening_cash=opening,
                closing_cash=closing,
                net_cash_movement=net_movement,
                net_operating=amounts["OPERATING"],
                net_investing=amounts["INVESTING"],
                net_financing=amounts["FINANCING"],
                exchange_effect=amounts["EXCHANGE_EFFECT"],
                classified_journal_count=classified,
                issues=tuple(issues),
                ready=not issues,
            )
            return preflight, tuple(all_events)
