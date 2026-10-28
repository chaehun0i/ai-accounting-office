"""POSTED 장부의 현금 범위를 명시적 설정으로 사전 점검합니다."""

import json
import re
from dataclasses import asdict
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.accounting.ledger.domain.entities import LedgerFact
from app.accounting.periods.domain.entities import Period
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
    CashPolicy,
    NoncashDisclosure,
)
from app.reporting.cash_flow.indirect import (
    POLICY_CODE,
    POLICY_VERSION,
    RULE_TYPES,
    AdjustmentRule,
    BridgeIssue,
    IndirectBridge,
    adjustments,
    policy_role,
    result_rule,
)
from app.reporting.cash_flow.snapshot import (
    CashDrilldown,
    CashLine,
    CashStatement,
    require_reconciled,
)
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.financial_statements.domain.rules import LINES, ReportSourceStale, calculate

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

    def policies(self, actor: Principal, company: UUID) -> tuple[CashPolicy, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return uow.cash_flow.policies(company)

    def set_policy(self, actor: Principal, company: UUID, effective_from: date,
                   interest_paid: str, interest_received: str, tax_paid: str,
                   expected_version: int) -> CashPolicy:
        if (interest_paid not in {"OPERATING", "FINANCING"}
                or interest_received not in {"OPERATING", "INVESTING"}
                or tax_paid not in {"OPERATING", "INVESTING", "FINANCING"}):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            uow.cash_flow.lock_configuration(company)
            history = uow.cash_flow.policies(company)
            version = history[-1].version if history else 0
            old = next((p for p in history if p.effective_from == effective_from), None)
            if old is not None and (old.interest_paid, old.interest_received, old.tax_paid) == (
                interest_paid, interest_received, tax_paid
            ) and old.version == expected_version + 1:
                return old
            if expected_version != version or (history and effective_from <= history[-1].effective_from):
                raise StateConflict()
            return uow.cash_flow.add_policy(
                company, CashPolicy(uuid4(), effective_from, interest_paid, interest_received,
                                    tax_paid, version + 1), actor.user_id, uow.now()
            )

    def noncash_disclosures(self, actor: Principal, company: UUID,
                            period_id: UUID) -> tuple[NoncashDisclosure, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            period, _, _, _, facts = ClosingService.closed_adjusted_source(uow, company, period_id)
            journals = {f.journal_id for f in facts if period.start_date <= f.entry_date
                        and f.source_type != "OPENING"}
            return tuple(d for d in uow.cash_flow.noncash(company) if d.journal_id in journals)

    def disclose_noncash(self, actor: Principal, company: UUID, journal_id: UUID,
                         debit_line_id: UUID, credit_line_id: UUID, evidence_id: UUID,
                         transaction_type: str, amount: Decimal) -> NoncashDisclosure:
        kinds = {"LEASE_ACQUISITION": ("ASSET", "LIABILITY"),
                 "IN_KIND_CAPITAL": ("ASSET", "EQUITY"),
                 "DEBT_TO_EQUITY": ("LIABILITY", "EQUITY")}
        if transaction_type not in kinds or not _valid_amount(amount):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            uow.cash_flow.lock_configuration(company)
            journal = uow.journals.get(company, journal_id)
            if journal is None:
                raise ResourceNotFound()
            if journal.status != "POSTED" or journal.source_type == "OPENING":
                raise StateConflict()
            _, _, _, _, facts = ClosingService.closed_adjusted_source(
                uow, company, journal.accounting_period_id
            )
            group = [f for f in facts if f.journal_id == journal_id]
            debit = next((f for f in group if f.line_id == debit_line_id), None)
            credit = next((f for f in group if f.line_id == credit_line_id), None)
            cash = {r.account_id for r in uow.cash_flow.scopes(company)}
            types = {a.id: a.account_type for a in uow.accounts.list(company)}
            if (debit is None or credit is None
                    or any(f.account_id in cash for f in group)
                    or any(types[f.account_id] not in {"ASSET", "LIABILITY", "EQUITY"} for f in group)
                    or (types[debit.account_id], types[credit.account_id]) != kinds[transaction_type]
                    or debit.debit_amount <= ZERO or credit.credit_amount <= ZERO
                    or not uow.cash_flow.evidence_linked(company, journal_id, evidence_id)):
                raise InvalidInput()
            existing = [d for d in uow.cash_flow.noncash(company) if d.journal_id == journal_id]
            old = next((d for d in existing if (d.debit_line_id, d.credit_line_id) ==
                        (debit_line_id, credit_line_id)), None)
            if old is not None:
                if (old.amount, old.evidence_id, old.transaction_type) != (
                    amount, evidence_id, transaction_type
                ):
                    raise StateConflict()
                return old
            if (sum((d.amount for d in existing if d.debit_line_id == debit_line_id), ZERO) + amount
                    > debit.debit_amount or
                    sum((d.amount for d in existing if d.credit_line_id == credit_line_id), ZERO)
                    + amount > credit.credit_amount):
                raise InvalidInput()
            return uow.cash_flow.add_noncash(
                company, NoncashDisclosure(uuid4(), journal_id, debit_line_id, credit_line_id,
                                           evidence_id, transaction_type, amount),
                actor.user_id, uow.now()
            )

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
            uow.cash_flow.lock_configuration(company)
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
            if any(
                account_id in (row.account_id, row.related_account_id)
                for row in uow.cash_flow.adjustment_rules(company)
            ):
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
            uow.cash_flow.lock_configuration(company)
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

    def generate_snapshot(
        self,
        actor: Principal,
        company: UUID,
        period_id: UUID,
        statement_set_id: UUID,
        close_version: int,
        source_digest: str,
        mapping_digest: str,
        key: str,
    ) -> CashStatement:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            uow.cash_flow.lock_configuration(company)
            bridge = self._indirect_bridge(uow, company, period_id)
            if (
                bridge.statement_set_id,
                bridge.close_version,
                bridge.source_digest,
                bridge.mapping_digest,
            ) != (statement_set_id, close_version, source_digest, mapping_digest):
                raise ReportSourceStale()
            period, _, source, _, facts = ClosingService.closed_adjusted_source(
                uow, company, period_id
            )
            preflight, events = self._analyze_closed(uow, company, period, source, facts)
            require_reconciled(preflight, bridge)
            bs = uow.statements.statement(company, statement_set_id, "BALANCE_SHEET")
            income = uow.statements.statement(company, statement_set_id, "INCOME_STATEMENT")
            if bs is None or income is None:
                raise ReportSourceStale()
            fingerprint = digest(
                (
                    str(period_id),
                    str(statement_set_id),
                    close_version,
                    source_digest,
                    mapping_digest,
                )
            )
            replay = uow.cash_snapshots.replay(company, actor.user_id, key, fingerprint)
            if replay is not None:
                return replay
            result = uow.cash_snapshots.add(
                company,
                actor.user_id,
                uow.now(),
                preflight,
                bridge,
                events,
                ((bs.id, bs.snapshot_digest), (income.id, income.snapshot_digest)),
                facts,
                period.start_date,
            )
            uow.cash_snapshots.record(
                company, actor.user_id, key, fingerprint, result.id, uow.now()
            )
            return result

    def snapshot(self, actor: Principal, company: UUID, statement_id: UUID) -> CashStatement:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return uow.cash_snapshots.get(company, statement_id)

    def current_snapshot(self, actor: Principal, company: UUID, period_id: UUID) -> CashStatement:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            uow.cash_flow.lock_configuration(company)
            current = uow.cash_snapshots.current(company, period_id)
            bridge = self._indirect_bridge(uow, company, period_id)
            if bridge.status != "READY" or (
                current.statement_set_id,
                current.close_version,
                current.source_digest,
                current.mapping_digest,
            ) != (
                bridge.statement_set_id,
                bridge.close_version,
                bridge.source_digest,
                bridge.mapping_digest,
            ):
                raise ReportSourceStale()
            return current

    def snapshot_lines(
        self, actor: Principal, company: UUID, statement_id: UUID
    ) -> tuple[CashLine, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return uow.cash_snapshots.lines(company, statement_id)

    def snapshot_drilldown(
        self,
        actor: Principal,
        company: UUID,
        statement_id: UUID,
        line_id: UUID | None = None,
    ) -> CashDrilldown:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return uow.cash_snapshots.drilldown(company, statement_id, line_id)

    def adjustment_rules(self, actor: Principal, company: UUID) -> tuple[AdjustmentRule, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return uow.cash_flow.adjustment_rules(company)

    def map_adjustment(
        self,
        actor: Principal,
        company: UUID,
        account_id: UUID,
        adjustment_code: str,
        source_mapping_type: str,
        related_account_id: UUID | None,
        effective_from: date,
        effective_to: date | None,
        policy_code: str,
        policy_version: int,
    ) -> AdjustmentRule:
        if (
            adjustment_code not in RULE_TYPES
            or source_mapping_type
            not in {"ACCOUNT_LEDGER", "ASSET_REGISTER", "INVENTORY_SUBLEDGER"}
            or policy_code != POLICY_CODE
            or policy_version != POLICY_VERSION
            or (effective_to is not None and effective_to < effective_from)
            or (adjustment_code == "NONCASH_PAIR") != (related_account_id is not None)
            or account_id == related_account_id
        ):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            uow.cash_flow.lock_configuration(company)
            account = uow.accounts.get_locked(company_id=company, resource_id=account_id)
            if account is None:
                raise ResourceNotFound()
            allowed = (
                {"REVENUE", "EXPENSE"}
                if result_rule(adjustment_code)
                else {"ASSET", "LIABILITY"}
                if adjustment_code == "WORKING_CAPITAL" or adjustment_code.endswith("_BALANCE")
                else {"ASSET", "LIABILITY", "EQUITY"}
            )
            cash_accounts = {row.account_id for row in uow.cash_flow.scopes(company)}
            if (
                account.account_type not in allowed
                or not account.posting_allowed
                or account.status != "ACTIVE"
                or account_id in cash_accounts
            ):
                raise InvalidInput()
            if related_account_id is not None:
                related = uow.accounts.get(company_id=company, resource_id=related_account_id)
                if related is None:
                    raise ResourceNotFound()
                if (
                    related.account_type not in {"ASSET", "LIABILITY"}
                    or not related.posting_allowed
                    or related.status != "ACTIVE"
                    or related_account_id in cash_accounts
                ):
                    raise InvalidInput()
            rule = AdjustmentRule(
                uuid4(),
                account_id,
                adjustment_code,
                source_mapping_type,
                related_account_id,
                effective_from,
                effective_to,
                1,
                policy_code,
                policy_version,
            )
            old = next(
                (r for r in uow.cash_flow.adjustment_rules(company) if r.account_id == account_id),
                None,
            )
            if old is not None:
                from dataclasses import replace

                if replace(rule, id=old.id) != old:
                    raise StateConflict()
                return old
            return uow.cash_flow.add_adjustment_rule(company, rule, actor.user_id, uow.now())

    def indirect_bridge(self, actor: Principal, company: UUID, period_id: UUID) -> IndirectBridge:
        """Read-only bridge from one locked CLOSED source; this is not a CF snapshot."""
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return self._indirect_bridge(uow, company, period_id)

    def _indirect_bridge(
        self, uow: CashFlowUnitOfWork, company: UUID, period_id: UUID
    ) -> IndirectBridge:
        try:
            period, run, source_digest, rows, facts = ClosingService.closed_adjusted_source(
                uow, company, period_id
            )
        except ClosingRunStale:
            raise ReportSourceStale() from None
        preflight, events = self._analyze_closed(uow, company, period, source_digest, facts)
        rules = uow.cash_flow.adjustment_rules(company)
        account_types = {a.id: a.account_type for a in uow.accounts.list(company)}
        policy = next((p for p in reversed(uow.cash_flow.policies(company))
                       if p.effective_from <= period.start_date), None)
        policy_activities = ({"INTEREST_PAID": policy.interest_paid,
                              "INTEREST_RECEIVED": policy.interest_received,
                              "TAX_PAID": policy.tax_paid} if policy else {})
        result, adjustment_issues = adjustments(
            facts,
            rules,
            account_types,
            {r.account_id for r in uow.cash_flow.scopes(company)},
            period.start_date,
            period.end_date,
            uow.cash_flow.noncash(company),
            policy_activities,
        )
        issues = [BridgeIssue(i.code, journal_id=i.journal_id) for i in preflight.issues]
        issues.extend(adjustment_issues)
        rules_by_account = {r.account_id: r for r in rules}
        for event in events:
            rule = rules_by_account.get(event.counterpart_account_id)
            role = policy_role(rule.adjustment_code) if rule else None
            if role is not None and event.activity_type != policy_activities.get(role):
                issues.append(BridgeIssue("INDIRECT_DIRECT_POLICY_MISMATCH",
                                          event.counterpart_account_id, event.journal_id))
            if rule is not None and (
                (
                    rule.adjustment_code in {"OPERATING_RESULT", "WORKING_CAPITAL"}
                    and event.activity_type != "OPERATING"
                )
                or (
                    rule.adjustment_code == "EXCLUDED_BALANCE"
                    and event.activity_type == "OPERATING"
                )
            ):
                issues.append(
                    BridgeIssue(
                        "INDIRECT_DIRECT_POLICY_MISMATCH",
                        event.counterpart_account_id,
                        event.journal_id,
                    )
                )
        current = next(
            (
                s
                for s in uow.statements.sets(company, period_id)
                if s.close_version == period.close_version
            ),
            None,
        )
        statement_sources: list[tuple[str, str, str]] = []
        snapshots = uow.cash_flow.statement_snapshot_sources(company, current.id) if current else ()
        net_profit: Decimal | None = None
        if current is None:
            issues.append(BridgeIssue("INDIRECT_STATEMENT_SOURCE_MISSING"))
        else:
            mappings = uow.statements.mappings(company, current.taxonomy_id, period.end_date)
            mapping_digest = digest([(str(a), code, version) for a, code, version in mappings])
            taxonomy = uow.statements.active_taxonomy(period.end_date)
            if (
                current.trial_balance_digest != source_digest
                or current.closing_run_id != run.id
                or current.mapping_digest != mapping_digest
                or taxonomy != (current.taxonomy_id, current.taxonomy_version)
                or current.status != "GENERATED"
                or [item[2] for item in snapshots] != ["BALANCE_SHEET", "INCOME_STATEMENT"]
                or any(
                    item[3] != 1 or item[4] != source_digest or item[5] != mapping_digest
                    for item in snapshots
                )
                or not uow.cash_flow.statement_line_sources_valid(
                    company, current.id, source_digest
                )
            ):
                issues.append(BridgeIssue("INDIRECT_STATEMENT_SOURCE_STALE"))
            else:
                expected = calculate(rows, [(a, c) for a, c, _ in mappings], account_types)
                for kind in ("BALANCE_SHEET", "INCOME_STATEMENT"):
                    view = uow.statements.statement(company, current.id, kind)
                    if view is None:
                        issues.append(BridgeIssue("INDIRECT_STATEMENT_SOURCE_MISSING"))
                        continue
                    statement_sources.append((kind, str(view.id), view.snapshot_digest))
                    definitions = [line for line in LINES if line.statement_type == kind]
                    if (
                        view.status != "GENERATED"
                        or [line.line_code for line in view.lines]
                        != [line.line_code for line in definitions]
                        or any(
                            line.current_amount != expected.get(line.line_code)
                            for line in view.lines
                        )
                        or digest(
                            [
                                (line.line_code, str(expected[line.line_code]))
                                for line in definitions
                            ]
                        )
                        != view.snapshot_digest
                    ):
                        issues.append(BridgeIssue("INDIRECT_STATEMENT_SOURCE_STALE"))
                    if kind == "INCOME_STATEMENT":
                        net_profit = next(
                            (
                                line.current_amount
                                for line in view.lines
                                if line.line_code == "NET_PROFIT"
                            ),
                            None,
                        )
                if net_profit is None:
                    issues.append(BridgeIssue("INDIRECT_STATEMENT_SOURCE_MISSING"))
        net_operating = (
            net_profit + sum((row.amount for row in result), ZERO)
            if net_profit is not None
            else None
        )
        difference = net_operating - preflight.net_operating if net_operating is not None else None
        if difference is not None and difference != ZERO:
            issues.append(BridgeIssue("INDIRECT_OPERATING_RECONCILIATION_MISMATCH"))
        return IndirectBridge(
            period_id,
            current.id if current else None,
            period.close_version,
            source_digest,
            digest(
                (
                    preflight.mapping_digest,
                    (
                        str(current.id),
                        str(current.closing_run_id),
                        current.close_version,
                        str(current.taxonomy_id),
                        current.taxonomy_version,
                        current.trial_balance_digest,
                        current.mapping_digest,
                    )
                    if current
                    else None,
                    statement_sources,
                    snapshots,
                    [
                        (
                            str(r.id),
                            str(r.account_id),
                            r.adjustment_code,
                            r.source_mapping_type,
                            str(r.related_account_id) if r.related_account_id else None,
                            r.effective_from.isoformat(),
                            r.effective_to.isoformat() if r.effective_to else None,
                            r.version,
                            r.policy_code,
                            r.policy_version,
                        )
                        for r in rules
                    ],
                )
            ),
            "COMPANY_CASH_POLICY" if policy else POLICY_CODE,
            policy.version if policy else POLICY_VERSION,
            net_profit,
            result,
            net_operating,
            preflight.net_operating,
            difference,
            tuple(issues),
            "BLOCKED" if issues else "READY",
        )

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
            uow.cash_flow.lock_configuration(company)
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
            uow.cash_flow.lock_configuration(company)
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
            return self._analyze_closed(uow, company, period, source_digest, facts)

    @staticmethod
    def _analyze_closed(
        uow: CashFlowUnitOfWork,
        company: UUID,
        period: Period,
        source_digest: str,
        facts: list[LedgerFact],
    ) -> tuple[CashPreflight, tuple[CashEvent, ...]]:
        scopes = uow.cash_flow.scopes(company)
        classes = uow.cash_flow.classifications(company)
        allocations = uow.cash_flow.allocations(company)
        policies = uow.cash_flow.policies(company)
        noncash = uow.cash_flow.noncash(company)
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
                json.loads(json.dumps([asdict(p) for p in policies
                                       if p.effective_from <= period.end_date], default=str)),
                json.loads(json.dumps([asdict(d) for d in noncash
                                       if d.journal_id in period_journal_ids], default=str)),
            )
        )
        issues: list[CashPreflightIssue] = []
        if any(period.start_date < p.effective_from <= period.end_date for p in policies):
            issues.append(CashPreflightIssue("CASH_POLICY_NOT_FULL_PERIOD"))
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
        rules = {r.account_id: r for r in uow.cash_flow.adjustment_rules(company)}
        for journal_id, journal_facts in by_journal.items():
            cash = [f for f in journal_facts if f.account_id in cash_accounts]
            if not cash:
                journal_disclosures = [d for d in noncash if d.journal_id == journal_id]
                if journal_disclosures:
                    disclosed: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
                    for d in journal_disclosures:
                        disclosed[d.debit_line_id] += d.amount
                        disclosed[d.credit_line_id] -= d.amount
                    if any(f.debit_amount - f.credit_amount != disclosed[f.line_id]
                           for f in journal_facts):
                        issues.append(CashPreflightIssue("NONCASH_DISCLOSURE_INCOMPLETE", journal_id))
                elif any(f.account_id in rules and
                         rules[f.account_id].adjustment_code == "EXCLUDED_BALANCE"
                         for f in journal_facts) and not any(
                    f.account_id in rules and rules[f.account_id].adjustment_code == "NONCASH_PAIR"
                    for f in journal_facts
                ):
                    issues.append(CashPreflightIssue("NONCASH_DISCLOSURE_MISSING", journal_id))
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
            period_id=period.id,
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
