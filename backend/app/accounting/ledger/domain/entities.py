"""확정 분개에서만 원장과 시산표를 결정론적으로 계산합니다."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.accounting.journals.domain.errors import AccountingError


@dataclass(frozen=True, kw_only=True)
class LedgerFact:
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
    counterparty_name: str | None = None


@dataclass(frozen=True, kw_only=True)
class LedgerRow(LedgerFact):
    running_balance: Decimal


@dataclass(frozen=True, kw_only=True)
class TrialRow:
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


def ledger(facts: list[LedgerFact], date_from: date) -> list[LedgerRow]:
    from dataclasses import asdict

    result = []
    balance = Decimal("0")
    for f in facts:
        balance += f.debit_amount - f.credit_amount
        if f.entry_date >= date_from:
            result.append(
                LedgerRow(
                    **asdict(f),
                    running_balance=balance if f.normal_balance == "DEBIT" else -balance,
                )
            )
    return result


def trial_balance(facts: list[LedgerFact], date_from: date) -> list[TrialRow]:
    groups: dict[UUID, list[LedgerFact]] = {}
    for fact in facts:
        groups.setdefault(fact.account_id, []).append(fact)
    result = []
    zero = Decimal("0")
    for group in groups.values():
        first = group[0]
        opening = sum(
            (f.debit_amount - f.credit_amount for f in group if f.entry_date < date_from), zero
        )
        debit = sum((f.debit_amount for f in group if f.entry_date >= date_from), zero)
        credit = sum((f.credit_amount for f in group if f.entry_date >= date_from), zero)
        end = opening + debit - credit
        result.append(
            TrialRow(
                account_id=first.account_id,
                account_code=first.account_code,
                account_name=first.account_name,
                normal_balance=first.normal_balance,
                opening_debit=max(opening, zero),
                opening_credit=max(-opening, zero),
                period_debit=debit,
                period_credit=credit,
                ending_debit=max(end, zero),
                ending_credit=max(-end, zero),
                ending_balance=end if first.normal_balance == "DEBIT" else -end,
            )
        )
    for d, c in [
        ("opening_debit", "opening_credit"),
        ("period_debit", "period_credit"),
        ("ending_debit", "ending_credit"),
    ]:
        if sum((getattr(r, d) for r in result), zero) != sum((getattr(r, c) for r in result), zero):
            raise AccountingError(
                "JOURNAL_NOT_BALANCED",
                "장부의 차변과 대변이 일치하지 않습니다. 관리자에게 확인을 요청해 주세요.",
                500,
            )
    return sorted(result, key=lambda r: r.account_code)
