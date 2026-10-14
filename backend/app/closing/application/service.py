"""기존 장부·금융 계산을 조합해 월마감의 사람 승인과 잠금을 관리합니다."""

import re
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.accounting.journals.application.commands import JournalCommands
from app.accounting.journals.application.service import validate_journal
from app.accounting.journals.domain.entities import Journal, JournalLine
from app.accounting.journals.domain.errors import AccountingError
from app.accounting.ledger.domain.entities import LedgerFact, TrialRow, trial_balance
from app.accounting.periods.domain.entities import Period
from app.closing.application.contracts import ClosingUnitOfWork
from app.closing.domain.entities import (
    ClosingAdjustment,
    ClosingApproval,
    ClosingCheckResult,
    ClosingRun,
    ClosingSnapshot,
)
from app.closing.domain.errors import (
    ClosingAdjustmentIncomplete,
    ClosingBlockersRemain,
    ClosingRunStale,
    PeriodAlreadyClosed,
    PeriodNotClosing,
)
from app.closing.domain.rules import ADJUSTMENT_TYPES, stable_digest, transition_period
from app.companies.application.service import require_company
from app.contracts.access_errors import (
    AuthorizationDenied,
    InvalidInput,
    ResourceNotFound,
    StateConflict,
)
from app.finance.reconciliation.application.bank_service import BankReconciliationService
from app.finance.reconciliation.application.service import FinanceReports
from app.identity.users.domain.entities import Principal

ZERO = Decimal("0")


def _key(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value):
        raise InvalidInput()
    return value


def _check(code: str, blocked: bool, amount: Decimal = ZERO) -> ClosingCheckResult:
    return ClosingCheckResult(
        check_code=code,
        severity="BLOCKER" if blocked else "PASS",
        result_code=code if blocked else "OK",
        amount_impact=abs(amount),
        source_type=None,
        source_id=None,
        evidence_ref=None,
    )


def _facts_digest(facts: list[LedgerFact]) -> str:
    return stable_digest(
        [
            (
                str(f.journal_id),
                str(f.line_id),
                str(f.account_id),
                str(f.debit_amount),
                str(f.credit_amount),
                f.entry_date.isoformat(),
            )
            for f in facts
        ]
    )


class ClosingService:
    def __init__(
        self,
        factory: Callable[[], ClosingUnitOfWork],
        journal_commands: JournalCommands | None = None,
    ) -> None:
        self.factory = factory
        self.journal_commands = journal_commands

    @staticmethod
    def _period(uow: ClosingUnitOfWork, company: UUID, period_id: UUID) -> Period:
        period = uow.periods.get(company_id=company, resource_id=period_id)
        if period is None:
            raise ResourceNotFound()
        return period

    @staticmethod
    def _snapshot(
        uow: ClosingUnitOfWork, company: UUID, period_id: UUID, run_id: UUID | None
    ) -> ClosingSnapshot:
        period = ClosingService._period(uow, company, period_id)
        facts = uow.ledger.facts(company, period.end_date)
        fact_digest = _facts_digest(facts)
        tb_error = False
        try:
            trial_balance(facts, period.start_date)
        except AccountingError:
            tb_error = True
        transaction_count, journal_count = uow.closing.pending(
            company, period.start_date, period.end_date
        )
        cutoff_count = uow.closing.cutoff_count(company, period.start_date, period.end_date)
        bank_summaries = [
            BankReconciliationService._summary(uow, company, statement.id)
            for statement in uow.banking.statements(company)
            if period.start_date <= statement.statement_end <= period.end_date
        ]
        bank_statement_status = [
            statement.status
            for statement in uow.banking.statements(company)
            if period.start_date <= statement.statement_end <= period.end_date
        ]
        card_summaries = [
            BankReconciliationService.card_summary_in(uow, company, account.id, period.end_date)
            for account in uow.banking.accounts(company, "CARD")
        ]
        bank_digest = stable_digest(
            [asdict(value) for value in bank_summaries]
            + [asdict(value) for value in card_summaries]
            + bank_statement_status
        )
        ar = FinanceReports.reconcile_in(uow, company, "AR", period.end_date)
        ap = FinanceReports.reconcile_in(uow, company, "AP", period.end_date)
        ar_digest = stable_digest(asdict(ar))
        ap_digest = stable_digest(asdict(ap))
        adjustments = uow.closing.adjustments(company, run_id) if run_id else []
        adjustment_journals = [
            uow.journals.get(company, adjustment.proposed_journal_id) for adjustment in adjustments
        ]
        incomplete = any(
            adj.required and (journal is None or journal.status != "POSTED")
            for adj, journal in zip(adjustments, adjustment_journals, strict=True)
        )
        bank_blocker = (
            any(summary.blocker for summary in bank_summaries)
            or any(status != "CLOSED" for status in bank_statement_status)
            or any(summary.blocker for summary in card_summaries)
        )
        checks = (
            _check("TRANSACTIONS_PENDING", transaction_count > 0, Decimal(transaction_count)),
            _check("JOURNALS_PENDING", journal_count > 0, Decimal(journal_count)),
            _check("BANK_CARD_UNRECONCILED", bank_blocker),
            _check("AR_GL_MISMATCH", ar.status != "MATCHED", ar.difference),
            _check("AP_GL_MISMATCH", ap.status != "MATCHED", ap.difference),
            _check("TRIAL_BALANCE_UNBALANCED", tb_error),
            _check(
                "ADJUSTMENT_INCOMPLETE", incomplete, Decimal(sum(a.required for a in adjustments))
            ),
            ClosingCheckResult(
                check_code="CUTOFF_REVIEW",
                severity="WARNING" if cutoff_count else "PASS",
                result_code="DATE_DIFFERS" if cutoff_count else "OK",
                amount_impact=Decimal(cutoff_count),
                source_type=None,
                source_id=None,
                evidence_ref=None,
            ),
        )
        source_digest = stable_digest(
            (
                fact_digest,
                bank_digest,
                ar_digest,
                ap_digest,
                [
                    (a.id, a.version, j.status if j else "MISSING")
                    for a, j in zip(adjustments, adjustment_journals, strict=True)
                ],
                [(c.check_code, c.severity, str(c.amount_impact)) for c in checks],
            )
        )
        return ClosingSnapshot(
            source_digest=source_digest,
            tb_digest=fact_digest,
            bank_digest=bank_digest,
            ar_digest=ar_digest,
            ap_digest=ap_digest,
            checks=checks,
        )

    @staticmethod
    def _fresh(uow: ClosingUnitOfWork, run: ClosingRun) -> ClosingSnapshot:
        snapshot = ClosingService._snapshot(uow, run.company_id, run.accounting_period_id, run.id)
        if snapshot.source_digest != run.source_digest:
            raise ClosingRunStale()
        return snapshot

    @staticmethod
    def _sync_adjustments(uow: ClosingUnitOfWork, company: UUID, run_id: UUID) -> None:
        for adjustment in uow.closing.adjustments(company, run_id):
            journal = uow.journals.get(company, adjustment.proposed_journal_id)
            if journal is not None and journal.status == "POSTED" and adjustment.status != "POSTED":
                uow.closing.update_adjustment(
                    replace(
                        adjustment,
                        status="POSTED",
                        approval_id=journal.approval_id,
                        version=adjustment.version + 1,
                    ),
                    adjustment.version,
                )

    @staticmethod
    def _reviewer_still_authorized(
        uow: ClosingUnitOfWork,
        company: UUID,
        approval: ClosingApproval,
        permission: str,
    ) -> None:
        if approval.reviewer_id is None:
            raise AuthorizationDenied()
        access = uow.companies.accessible(approval.reviewer_id, company, lock=True)
        reviewer = uow.users.get(approval.reviewer_id, lock=True)
        if access is None or reviewer is None or reviewer.status != "ACTIVE":
            raise AuthorizationDenied()
        if permission not in access.permissions:
            raise AuthorizationDenied()

    def periods(self, actor: Principal, company: UUID) -> list[Period]:
        with self.factory() as uow:
            require_company(uow, actor, company, "period.read")
            return uow.periods.list(company)

    def history(self, actor: Principal, company: UUID, period_id: UUID) -> list[ClosingRun]:
        with self.factory() as uow:
            require_company(uow, actor, company, "period.read")
            self._period(uow, company, period_id)
            return uow.closing.runs(company, period_id)

    def detail(
        self, actor: Principal, company: UUID, identifier: UUID
    ) -> tuple[ClosingRun, tuple[ClosingCheckResult, ...], list[ClosingAdjustment]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "period.read")
            run = uow.closing.run(company, identifier)
            if run is None:
                raise ResourceNotFound()
            return (
                run,
                uow.closing.checks(company, identifier),
                uow.closing.adjustments(company, identifier),
            )

    def approvals(self, actor: Principal, company: UUID, run_id: UUID) -> list[ClosingApproval]:
        with self.factory() as uow:
            require_company(uow, actor, company, "period.read")
            if uow.closing.run(company, run_id) is None:
                raise ResourceNotFound()
            return uow.closing.approvals(company, run_id)

    def start(self, actor: Principal, company: UUID, period_id: UUID, key: str) -> ClosingRun:
        key = _key(key)
        fingerprint = stable_digest(("start", str(period_id)))
        with self.factory() as uow:
            require_company(uow, actor, company, "period.start_closing")
            uow.lock_period(company, period_id)
            uow.banking.lock(company)
            uow.lock_command(company, actor.user_id, "closing.start", key)
            replay = uow.closing.replay(company, actor.user_id, "closing.start", key, fingerprint)
            if replay:
                run = uow.closing.run(company, replay[0])
                assert run is not None
                return run
            period = self._period(uow, company, period_id)
            if period.status != "OPEN":
                raise StateConflict()
            old = uow.closing.runs(company, period_id)
            now = uow.now()
            result = ClosingRun(
                id=uuid4(),
                company_id=company,
                accounting_period_id=period_id,
                run_version=old[0].run_version + 1 if old else 1,
                status="ACTIVE",
                source_digest="",
                unadjusted_tb_digest="",
                adjusted_tb_digest=None,
                bank_reconciliation_digest="",
                ar_reconciliation_digest="",
                ap_reconciliation_digest="",
                created_by=actor.user_id,
                created_at=now,
                completed_at=None,
            )
            snapshot = self._snapshot(uow, company, period_id, None)
            result = replace(
                result,
                source_digest=snapshot.source_digest,
                unadjusted_tb_digest=snapshot.tb_digest,
                bank_reconciliation_digest=snapshot.bank_digest,
                ar_reconciliation_digest=snapshot.ar_digest,
                ap_reconciliation_digest=snapshot.ap_digest,
            )
            uow.closing.add_run(result)
            uow.closing.replace_checks(company, result.id, snapshot.checks, now)
            changed = replace(
                period,
                status=transition_period(period.status, "start"),
                version=period.version + 1,
                updated_at=now,
            )
            if not uow.periods.update(changed, period.version):
                raise StateConflict()
            uow.closing.record(
                company,
                actor.user_id,
                "closing.start",
                key,
                fingerprint,
                result.id,
                now,
                before=str(period.version),
                after=result.source_digest,
            )
            return result

    def rerun(self, actor: Principal, company: UUID, identifier: UUID, key: str) -> ClosingRun:
        key = _key(key)
        fingerprint = stable_digest(("rerun", str(identifier)))
        with self.factory() as uow:
            require_company(uow, actor, company, "period.start_closing")
            run = uow.closing.run(company, identifier)
            if run is None:
                raise ResourceNotFound()
            uow.lock_period(company, run.accounting_period_id)
            uow.banking.lock(company)
            uow.lock_command(company, actor.user_id, "closing.rerun", key)
            if uow.closing.replay(company, actor.user_id, "closing.rerun", key, fingerprint):
                result = uow.closing.run(company, identifier)
                assert result is not None
                return result
            if self._period(uow, company, run.accounting_period_id).status != "CLOSING":
                raise PeriodNotClosing()
            if run.status == "COMPLETED":
                raise StateConflict()
            for approval in uow.closing.approvals(company, run.id):
                if approval.action_code == "CLOSE" and approval.status in {"PENDING", "APPROVED"}:
                    uow.closing.update_approval(replace(approval, status="REJECTED"))
            self._sync_adjustments(uow, company, run.id)
            snapshot = self._snapshot(uow, company, run.accounting_period_id, run.id)
            result = replace(
                run,
                status="ACTIVE",
                source_digest=snapshot.source_digest,
                adjusted_tb_digest=snapshot.tb_digest,
                bank_reconciliation_digest=snapshot.bank_digest,
                ar_reconciliation_digest=snapshot.ar_digest,
                ap_reconciliation_digest=snapshot.ap_digest,
            )
            uow.closing.update_run(result)
            uow.closing.replace_checks(company, run.id, snapshot.checks, uow.now())
            uow.closing.record(
                company,
                actor.user_id,
                "closing.rerun",
                key,
                fingerprint,
                run.id,
                uow.now(),
                before=run.source_digest,
                after=result.source_digest,
            )
            return result

    def propose_adjustment(
        self,
        actor: Principal,
        company: UUID,
        run_id: UUID,
        kind: str,
        entry_date: date,
        description: str,
        lines: tuple[JournalLine, ...],
        auto_reverse: bool,
        reversal_date: date | None,
        key: str,
    ) -> ClosingAdjustment:
        key = _key(key)
        if (
            kind not in ADJUSTMENT_TYPES
            or not description.strip()
            or (auto_reverse and reversal_date is None)
        ):
            raise InvalidInput()
        fingerprint = stable_digest(
            (
                str(run_id),
                kind,
                entry_date,
                description,
                [asdict(line) for line in lines],
                auto_reverse,
                reversal_date,
            )
        )
        with self.factory() as uow:
            require_company(uow, actor, company, "period.start_closing")
            require_company(uow, actor, company, "journal.propose")
            run = uow.closing.run(company, run_id)
            if run is None:
                raise ResourceNotFound()
            uow.lock_period(company, run.accounting_period_id)
            uow.lock_command(company, actor.user_id, "closing.adjustment", key)
            replay = uow.closing.replay(
                company, actor.user_id, "closing.adjustment", key, fingerprint
            )
            if replay and replay[1]:
                result = uow.closing.adjustment(company, replay[1])
                assert result is not None
                return result
            if (
                self._period(uow, company, run.accounting_period_id).status != "CLOSING"
                or run.status != "ACTIVE"
            ):
                raise PeriodNotClosing()
            now = uow.now()
            journal = Journal(
                id=uuid4(),
                company_id=company,
                accounting_period_id=run.accounting_period_id,
                entry_date=entry_date,
                description=description,
                source_type="CLOSING",
                proposal_origin="HUMAN",
                status="DRAFT",
                version=1,
                created_by=actor.user_id,
                created_at=now,
                updated_at=now,
                lines=lines,
            )
            validate_journal(uow, journal, balanced=False)
            uow.journals.add(journal)
            result = ClosingAdjustment(
                id=uuid4(),
                company_id=company,
                closing_run_id=run_id,
                adjustment_type=kind,
                status="PROPOSED",
                proposed_journal_id=journal.id,
                approval_id=None,
                required=True,
                auto_reverse=auto_reverse,
                scheduled_reversal_date=reversal_date,
                reversal_journal_id=None,
                version=1,
            )
            uow.closing.add_adjustment(result, now, None, None)
            uow.closing.record(
                company,
                actor.user_id,
                "closing.adjustment",
                key,
                fingerprint,
                run_id,
                now,
                adjustment=result.id,
            )
            return result

    def request_approval(
        self, actor: Principal, company: UUID, run_id: UUID, action: str, reason: str, key: str
    ) -> ClosingApproval:
        key = _key(key)
        if action not in {"CLOSE", "REOPEN"} or not reason.strip():
            raise InvalidInput()
        permission = "period.close" if action == "CLOSE" else "period.reopen.request"
        code = "closing.request." + action.lower()
        fingerprint = stable_digest((str(run_id), action, reason))
        with self.factory() as uow:
            require_company(uow, actor, company, permission)
            run = uow.closing.run(company, run_id)
            if run is None:
                raise ResourceNotFound()
            uow.lock_period(company, run.accounting_period_id)
            uow.banking.lock(company)
            uow.lock_command(company, actor.user_id, code, key)
            replay = uow.closing.replay(company, actor.user_id, code, key, fingerprint)
            if replay and replay[2]:
                result = uow.closing.approval(company, replay[2])
                assert result is not None
                return result
            period = self._period(uow, company, run.accounting_period_id)
            if action == "CLOSE":
                if period.status != "CLOSING" or run.status != "ACTIVE":
                    raise PeriodNotClosing()
                self._fresh(uow, run)
                checks = uow.closing.checks(company, run.id)
                if any(c.severity == "BLOCKER" for c in checks):
                    raise ClosingBlockersRemain()
                target = run.source_digest
            else:
                if period.status != "CLOSED" or run.status != "COMPLETED":
                    raise PeriodAlreadyClosed()
                target = stable_digest((run.source_digest, period.close_version))
            now = uow.now()
            result = ClosingApproval(
                id=uuid4(),
                company_id=company,
                closing_run_id=run_id,
                action_code=action,
                status="PENDING",
                target_digest=target,
                requester_id=actor.user_id,
                reviewer_id=None,
                requested_at=now,
                decided_at=None,
                reason=reason,
            )
            uow.closing.add_approval(result)
            if action == "CLOSE":
                uow.closing.update_run(replace(run, status="SUBMITTED"))
            uow.closing.record(
                company,
                actor.user_id,
                code,
                key,
                fingerprint,
                run.id,
                now,
                approval=result.id,
                after=target,
            )
            return result

    def approve(
        self, actor: Principal, company: UUID, approval_id: UUID, reason: str, key: str
    ) -> ClosingApproval:
        key = _key(key)
        if not reason.strip():
            raise InvalidInput()
        with self.factory() as uow:
            approval = uow.closing.approval(company, approval_id)
            if approval is None:
                raise ResourceNotFound()
            permission = (
                "period.close" if approval.action_code == "CLOSE" else "period.reopen.approve"
            )
            require_company(uow, actor, company, permission)
            run = uow.closing.run(company, approval.closing_run_id)
            assert run is not None
            uow.lock_period(company, run.accounting_period_id)
            uow.banking.lock(company)
            fingerprint = stable_digest((str(approval_id), reason))
            uow.lock_command(company, actor.user_id, "closing.approve", key)
            replay = uow.closing.replay(company, actor.user_id, "closing.approve", key, fingerprint)
            if replay:
                result = uow.closing.approval(company, approval_id)
                assert result is not None
                return result
            if approval.status != "PENDING" or approval.requester_id == actor.user_id:
                raise AuthorizationDenied()
            period = self._period(uow, company, run.accounting_period_id)
            expected = (
                run.source_digest
                if approval.action_code == "CLOSE"
                else stable_digest((run.source_digest, period.close_version))
            )
            if approval.target_digest != expected:
                raise ClosingRunStale()
            if approval.action_code == "CLOSE":
                if period.status != "CLOSING" or run.status != "SUBMITTED":
                    raise PeriodNotClosing()
                self._fresh(uow, run)
            elif period.status != "CLOSED" or run.status != "COMPLETED":
                raise StateConflict()
            result = replace(
                approval,
                status="APPROVED",
                reviewer_id=actor.user_id,
                decided_at=uow.now(),
                reason=reason,
            )
            uow.closing.update_approval(result)
            if approval.action_code == "CLOSE":
                uow.closing.update_run(replace(run, status="APPROVED"))
            uow.closing.record(
                company,
                actor.user_id,
                "closing.approve",
                key,
                fingerprint,
                run.id,
                uow.now(),
                approval=approval.id,
            )
            return result

    def finish(
        self, actor: Principal, company: UUID, run_id: UUID, approval_id: UUID, key: str
    ) -> ClosingRun:
        key = _key(key)
        fingerprint = stable_digest((str(run_id), str(approval_id)))
        with self.factory() as uow:
            require_company(uow, actor, company, "period.close")
            run = uow.closing.run(company, run_id)
            if run is None:
                raise ResourceNotFound()
            uow.lock_period(company, run.accounting_period_id)
            uow.banking.lock(company)
            uow.lock_command(company, actor.user_id, "closing.finish", key)
            if uow.closing.replay(company, actor.user_id, "closing.finish", key, fingerprint):
                result = uow.closing.run(company, run_id)
                assert result is not None
                return result
            period = self._period(uow, company, run.accounting_period_id)
            if period.status != "CLOSING":
                raise PeriodNotClosing()
            approval = uow.closing.approval(company, approval_id, lock=True)
            if (
                approval is None
                or approval.closing_run_id != run_id
                or approval.action_code != "CLOSE"
                or approval.status != "APPROVED"
            ):
                raise AuthorizationDenied()
            self._reviewer_still_authorized(uow, company, approval, "period.close")
            if run.status != "APPROVED" or approval.target_digest != run.source_digest:
                raise ClosingRunStale()
            snapshot = self._fresh(uow, run)
            checks = uow.closing.checks(company, run_id)
            if any(c.severity == "BLOCKER" for c in checks):
                if any(
                    c.check_code == "ADJUSTMENT_INCOMPLETE" and c.severity == "BLOCKER"
                    for c in checks
                ):
                    raise ClosingAdjustmentIncomplete()
                raise ClosingBlockersRemain()
            now = uow.now()
            closed = replace(
                period,
                status=transition_period(period.status, "close"),
                close_version=period.close_version + 1,
                closed_at=now,
                closed_by=actor.user_id,
                version=period.version + 1,
                updated_at=now,
            )
            if not uow.periods.update(closed, period.version):
                raise StateConflict()
            result = replace(
                run, status="COMPLETED", completed_at=now, adjusted_tb_digest=snapshot.tb_digest
            )
            uow.closing.update_run(result)
            uow.closing.update_approval(replace(approval, status="CONSUMED"))
            uow.closing.record(
                company,
                actor.user_id,
                "closing.finish",
                key,
                fingerprint,
                run.id,
                now,
                approval=approval_id,
                before=run.source_digest,
                after=result.adjusted_tb_digest or "",
            )
            return result

    def reopen(
        self,
        actor: Principal,
        company: UUID,
        run_id: UUID,
        approval_id: UUID,
        reason: str,
        key: str,
    ) -> Period:
        key = _key(key)
        if not reason.strip():
            raise InvalidInput()
        fingerprint = stable_digest((str(run_id), str(approval_id), reason))
        with self.factory() as uow:
            require_company(uow, actor, company, "period.reopen.execute")
            run = uow.closing.run(company, run_id)
            if run is None:
                raise ResourceNotFound()
            uow.lock_period(company, run.accounting_period_id)
            uow.lock_command(company, actor.user_id, "closing.reopen", key)
            if uow.closing.replay(company, actor.user_id, "closing.reopen", key, fingerprint):
                return self._period(uow, company, run.accounting_period_id)
            period = self._period(uow, company, run.accounting_period_id)
            approval = uow.closing.approval(company, approval_id, lock=True)
            if period.status != "CLOSED" or run.status != "COMPLETED":
                raise StateConflict()
            if (
                approval is None
                or approval.closing_run_id != run_id
                or approval.action_code != "REOPEN"
                or approval.status != "APPROVED"
                or approval.target_digest
                != stable_digest((run.source_digest, period.close_version))
            ):
                raise AuthorizationDenied()
            self._reviewer_still_authorized(uow, company, approval, "period.reopen.approve")
            now = uow.now()
            opened = replace(
                period,
                status=transition_period(period.status, "reopen"),
                close_version=period.close_version + 1,
                closed_at=None,
                closed_by=None,
                version=period.version + 1,
                updated_at=now,
            )
            if not uow.periods.update(opened, period.version):
                raise StateConflict()
            uow.closing.update_approval(replace(approval, status="CONSUMED"))
            uow.closing.record(
                company,
                actor.user_id,
                "closing.reopen",
                key,
                fingerprint,
                run.id,
                now,
                approval=approval_id,
                before=run.source_digest,
                after=str(opened.close_version),
            )
            return opened

    def adjusted_trial_balance(
        self, actor: Principal, company: UUID, run_id: UUID, stage: str
    ) -> tuple[str, list[TrialRow]]:
        if stage not in {"UNADJUSTED", "ADJUSTED"}:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "ledger.read")
            run = uow.closing.run(company, run_id)
            if run is None:
                raise ResourceNotFound()
            period = self._period(uow, company, run.accounting_period_id)
            facts = uow.ledger.facts(company, period.end_date)
            if stage == "UNADJUSTED":
                adjustment_ids = {
                    a.proposed_journal_id for a in uow.closing.adjustments(company, run_id)
                }
                facts = [f for f in facts if f.journal_id not in adjustment_ids]
            rows = trial_balance(facts, period.start_date)
            calculated = _facts_digest(facts)
            return calculated, rows

    @staticmethod
    def closed_adjusted_source(
        uow: ClosingUnitOfWork, company: UUID, period_id: UUID
    ) -> tuple[Period, ClosingRun, str, list[TrialRow], list[LedgerFact]]:
        """동일 UoW에서 잠근 CLOSED 기간의 마감 장부와 출처를 제공합니다."""
        uow.lock_period(company, period_id)
        period = ClosingService._period(uow, company, period_id)
        if period.status != "CLOSED":
            raise StateConflict()
        runs = uow.closing.runs(company, period_id)
        if not runs or runs[0].status != "COMPLETED":
            raise ClosingRunStale()
        run = runs[0]
        facts = uow.ledger.facts(company, period.end_date)
        source_digest = _facts_digest(facts)
        if source_digest != run.adjusted_tb_digest:
            raise ClosingRunStale()
        return period, run, source_digest, trial_balance(facts, period.start_date), facts

    def propose_reversal(
        self,
        actor: Principal,
        company: UUID,
        adjustment_id: UUID,
        reason: str,
        key: str,
    ) -> Journal:
        """기존 역분개 명령으로 다음 열린 기간에 초안을 만들고 사람 승인에 맡깁니다."""
        key = _key(key)
        if not reason.strip() or self.journal_commands is None:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "journal.reverse")
            adjustment = uow.closing.adjustment(company, adjustment_id)
            if adjustment is None:
                raise ResourceNotFound()
            if not adjustment.auto_reverse or adjustment.scheduled_reversal_date is None:
                raise StateConflict()
            source = uow.journals.get(company, adjustment.proposed_journal_id)
            if source is None or source.status != "POSTED":
                raise StateConflict()
            if adjustment.reversal_journal_id:
                existing = uow.journals.get(company, adjustment.reversal_journal_id)
                if existing is None:
                    raise ResourceNotFound()
                return existing
        # 기존 Journal command가 승인·기간·역분개 유일성 계약을 소유합니다.
        result = self.journal_commands.execute(
            actor,
            company,
            source.id,
            "reverse",
            source.version,
            stable_digest((str(adjustment_id), key)),
            reason=reason,
            reversal_date=adjustment.scheduled_reversal_date,
        )
        with self.factory() as uow:
            require_company(uow, actor, company, "journal.reverse")
            current = uow.closing.adjustment(company, adjustment_id, lock=True)
            if current is None:
                raise ResourceNotFound()
            if current.reversal_journal_id and current.reversal_journal_id != result.id:
                raise StateConflict()
            if current.reversal_journal_id is None:
                uow.closing.update_adjustment(
                    replace(current, reversal_journal_id=result.id, version=current.version + 1),
                    current.version,
                )
                uow.closing.record(
                    company,
                    actor.user_id,
                    "closing.reversal",
                    key,
                    stable_digest((str(adjustment_id), reason)),
                    current.closing_run_id,
                    uow.now(),
                    adjustment=adjustment_id,
                    after=str(result.id),
                )
        return result
