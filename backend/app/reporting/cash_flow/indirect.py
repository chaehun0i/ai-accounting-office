"""Deterministic operating bridge; unsupported source families never become plugs."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.accounting.ledger.domain.entities import LedgerFact
from app.reporting.cash_flow.entities import NoncashDisclosure

ZERO = Decimal("0")
POLICY_CODE = "TAX_INTEREST_OPERATING"
POLICY_VERSION = 1
POLICY_ROLES = ("INTEREST_PAID", "INTEREST_RECEIVED", "TAX_PAID")
RULE_TYPES = {"OPERATING_RESULT", "NONCASH_PAIR", "WORKING_CAPITAL", "EXCLUDED_BALANCE",
              "DISPOSAL_RESULT"} | {f"{role}_{kind}" for role in POLICY_ROLES
                                    for kind in ("RESULT", "BALANCE")}


def policy_role(code: str) -> str | None:
    return next((role for role in POLICY_ROLES if code.startswith(role + "_")), None)


def result_rule(code: str) -> bool:
    return code in {"OPERATING_RESULT", "NONCASH_PAIR", "DISPOSAL_RESULT"} or code.endswith("_RESULT")


@dataclass(frozen=True)
class AdjustmentRule:
    id: UUID
    account_id: UUID
    adjustment_code: str
    source_mapping_type: str
    related_account_id: UUID | None
    effective_from: date
    effective_to: date | None
    version: int
    policy_code: str
    policy_version: int


@dataclass(frozen=True)
class BridgeIssue:
    code: str
    account_id: UUID | None = None
    journal_id: UUID | None = None


@dataclass(frozen=True)
class AdjustmentSource:
    journal_id: UUID
    journal_line_id: UUID
    entry_date: date
    signed_debit_amount: Decimal
    is_opening: bool


@dataclass(frozen=True)
class Adjustment:
    rule_id: UUID
    rule_version: int
    account_id: UUID
    adjustment_code: str
    opening_balance: Decimal
    closing_balance: Decimal
    amount: Decimal
    sources: tuple[AdjustmentSource, ...]


@dataclass(frozen=True)
class IndirectBridge:
    period_id: UUID
    statement_set_id: UUID | None
    close_version: int
    source_digest: str
    mapping_digest: str
    policy_code: str
    policy_version: int
    net_profit: Decimal | None
    adjustments: tuple[Adjustment, ...]
    net_operating: Decimal | None
    direct_net_operating: Decimal
    reconciliation_difference: Decimal | None
    issues: tuple[BridgeIssue, ...]
    status: str


def adjustments(
    facts: list[LedgerFact],
    rules: tuple[AdjustmentRule, ...],
    account_types: dict[UUID, str],
    cash_accounts: set[UUID],
    period_start: date,
    period_end: date,
    noncash: tuple[NoncashDisclosure, ...] = (),
    policy_activities: dict[str, str] | None = None,
) -> tuple[tuple[Adjustment, ...], tuple[BridgeIssue, ...]]:
    """Balances use debit-positive signs; WC adjustment is minus its movement.

    Noncash add-backs require a two-account journal relationship and cannot
    touch cash or working capital. WC journals can touch cash, operating P&L,
    or other WC accounts; capex/lease/conversion movements require future sources.
    """
    issues: list[BridgeIssue] = []
    by_account = {rule.account_id: rule for rule in rules}
    if len(by_account) != len(rules):
        issues.append(BridgeIssue("INDIRECT_RULE_DUPLICATED"))
    period_facts = [
        f
        for f in facts
        if period_start <= f.entry_date <= period_end and f.source_type != "OPENING"
    ]
    journals: dict[UUID, list[LedgerFact]] = defaultdict(list)
    for fact in period_facts:
        journals[fact.journal_id].append(fact)
    disclosed: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    for item in noncash:
        disclosed[item.debit_line_id] += item.amount
        disclosed[item.credit_line_id] -= item.amount
    policy_activities = policy_activities or {}
    used = {f.account_id for f in period_facts} - cash_accounts
    for account in sorted(used, key=str):
        if account not in by_account:
            issues.append(BridgeIssue("INDIRECT_RULE_MISSING", account))
    result: list[Adjustment] = []
    for rule in sorted(rules, key=lambda r: str(r.account_id)):
        if rule.account_id not in used:
            continue
        account_type = account_types.get(rule.account_id)
        if (
            rule.policy_code != POLICY_CODE
            or rule.policy_version != POLICY_VERSION
            or rule.version < 1
        ):
            issues.append(BridgeIssue("INDIRECT_POLICY_UNSUPPORTED", rule.account_id))
        if rule.source_mapping_type != "ACCOUNT_LEDGER":
            issues.append(BridgeIssue("INDIRECT_SOURCE_UNSUPPORTED", rule.account_id))
        if rule.effective_from > period_start or (
            rule.effective_to is not None and rule.effective_to < period_end
        ):
            issues.append(BridgeIssue("INDIRECT_RULE_NOT_FULL_PERIOD", rule.account_id))
        allowed = (
            {"REVENUE", "EXPENSE"}
            if result_rule(rule.adjustment_code)
            else {"ASSET", "LIABILITY"}
            if rule.adjustment_code == "WORKING_CAPITAL" or rule.adjustment_code.endswith("_BALANCE")
            else {"ASSET", "LIABILITY", "EQUITY"}
        )
        if rule.adjustment_code not in RULE_TYPES or account_type not in allowed:
            issues.append(BridgeIssue("INDIRECT_RULE_ACCOUNT_INVALID", rule.account_id))
        account_facts = [f for f in facts if f.account_id == rule.account_id]
        current = [f for f in period_facts if f.account_id == rule.account_id]
        opening = sum(
            (
                f.debit_amount - f.credit_amount
                for f in account_facts
                if f.entry_date < period_start or f.source_type == "OPENING"
            ),
            ZERO,
        )
        movement = sum((f.debit_amount - f.credit_amount for f in current), ZERO)
        cash_movement = movement - sum((disclosed[f.line_id] for f in current), ZERO)
        role = policy_role(rule.adjustment_code)
        if role is not None and role not in policy_activities:
            issues.append(BridgeIssue("INDIRECT_COMPANY_POLICY_MISSING", rule.account_id))
        if rule.adjustment_code == "NONCASH_PAIR":
            related = by_account.get(rule.related_account_id) if rule.related_account_id else None
            for journal_id in sorted({f.journal_id for f in current}, key=str):
                group = journals[journal_id]
                if (
                    related is None
                    or related.adjustment_code != "EXCLUDED_BALANCE"
                    or rule.related_account_id in cash_accounts
                    or {f.account_id for f in group} != {rule.account_id, rule.related_account_id}
                    or sum((f.debit_amount - f.credit_amount for f in group), ZERO) != ZERO
                ):
                    issues.append(
                        BridgeIssue(
                            "INDIRECT_NONCASH_RELATION_UNSUPPORTED", rule.account_id, journal_id
                        )
                    )
        if rule.adjustment_code == "DISPOSAL_RESULT":
            for journal_id in sorted({f.journal_id for f in current}, key=str):
                group = journals[journal_id]
                if not any(
                    account_types.get(f.account_id) == "ASSET"
                    and f.account_id not in cash_accounts
                    and f.account_id in by_account
                    and by_account[f.account_id].adjustment_code == "EXCLUDED_BALANCE"
                    for f in group
                ) or any(
                    f.account_id != rule.account_id
                    and f.account_id not in cash_accounts
                    and (f.account_id not in by_account or
                         by_account[f.account_id].adjustment_code != "EXCLUDED_BALANCE")
                    for f in group
                ):
                    issues.append(BridgeIssue("INDIRECT_DISPOSAL_SOURCE_UNSUPPORTED",
                                              rule.account_id, journal_id))
        if rule.adjustment_code == "WORKING_CAPITAL" or rule.adjustment_code.endswith("_BALANCE"):
            for journal_id in sorted({f.journal_id for f in current}, key=str):
                if any(
                    f.debit_amount - f.credit_amount != disclosed[f.line_id]
                    and
                    f.account_id not in cash_accounts
                    and (
                        f.account_id not in by_account
                        or by_account[f.account_id].adjustment_code
                        not in ({"WORKING_CAPITAL", "OPERATING_RESULT"} |
                                {f"{r}_{k}" for r in POLICY_ROLES for k in ("RESULT", "BALANCE")})
                    )
                    for f in journals[journal_id]
                ):
                    issues.append(
                        BridgeIssue(
                            "INDIRECT_WORKING_CAPITAL_SOURCE_UNSUPPORTED",
                            rule.account_id,
                            journal_id,
                        )
                    )
        amount = ZERO
        if rule.adjustment_code == "WORKING_CAPITAL" or (
            role is not None and rule.adjustment_code.endswith("_BALANCE")
            and policy_activities.get(role) == "OPERATING"
        ):
            amount = -cash_movement
        elif rule.adjustment_code in {"NONCASH_PAIR", "DISPOSAL_RESULT"} or (
            role is not None and rule.adjustment_code.endswith("_RESULT")
            and policy_activities.get(role) != "OPERATING"
        ):
            amount = movement
        result.append(
            Adjustment(
                rule.id,
                rule.version,
                rule.account_id,
                rule.adjustment_code,
                opening,
                opening + movement,
                amount,
                tuple(
                    AdjustmentSource(
                        f.journal_id,
                        f.line_id,
                        f.entry_date,
                        f.debit_amount - f.credit_amount,
                        f.entry_date < period_start or f.source_type == "OPENING",
                    )
                    for f in sorted(account_facts, key=lambda f: (f.entry_date, str(f.line_id)))
                ),
            )
        )
    return tuple(result), tuple(issues)
