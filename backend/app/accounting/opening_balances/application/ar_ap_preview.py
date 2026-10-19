"""기초 AR/AP 원천과 Opening 전표 입력을 승격 전에 대조합니다."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.intake.domain.digest import digest
from app.onboarding.domain.values import Cell


@dataclass(frozen=True)
class PreviewIssue:
    code: str
    section: str
    row_key: str
    message: str


@dataclass(frozen=True)
class PreviewTotal:
    role: str
    account_code: str
    counterparty_code: str
    opening_amount: Decimal
    item_amount: Decimal


@dataclass(frozen=True)
class ArApPreview:
    session_version: int
    source_digest: str
    as_of_date: date | None
    ready: bool
    issues: tuple[PreviewIssue, ...]
    totals: tuple[PreviewTotal, ...]


def preview_ar_ap(
    cells: list[Cell],
    version: int,
    mappings: dict[str, str],
    counterparties: set[str],
) -> ArApPreview:
    """역할 매핑과 거래처 코드로 집계하며 금액을 추측하거나 반올림하지 않습니다."""
    sections = ("Opening_Balances", "AR_Opening", "AP_Opening")
    source = sorted(
        (cell.field_code, cell.row_key, str(cell.value))
        for cell in cells
        if cell.field_code.split(".", 1)[0] in sections and cell.source_type != "DERIVED"
    )
    values = {(cell.field_code, cell.row_key): cell.value for cell in cells}
    issues: list[PreviewIssue] = []
    opening: dict[tuple[str, str, str], Decimal] = {}
    items: dict[tuple[str, str, str], Decimal] = {}
    days: set[date] = set()

    def value(section: str, row: str, field: str) -> object | None:
        return values.get((f"{section}.{field}", row))

    def issue(code: str, section: str, row: str, message: str) -> None:
        issues.append(PreviewIssue(code, section, row, message))

    opening_rows = sorted(
        {cell.row_key for cell in cells if cell.field_code == "Opening_Balances.account_code"}
    )
    for row in opening_rows:
        day = value("Opening_Balances", row, "as_of_date")
        if isinstance(day, date):
            days.add(day)
        else:
            issue("INVALID_CUTOVER_DATE", "Opening_Balances", row, "기초잔액 기준일이 필요합니다.")
        account = value("Opening_Balances", row, "account_code")
        counterparty = value("Opening_Balances", row, "counterparty_code")
        debit = value("Opening_Balances", row, "debit_amount")
        credit = value("Opening_Balances", row, "credit_amount")
        for role, mapped in mappings.items():
            if account != mapped:
                continue
            amount = debit if role == "AR" else credit
            opposite = credit if role == "AR" else debit
            if not isinstance(amount, Decimal) or amount <= 0 or opposite != Decimal(0):
                issue(
                    "INVALID_CONTROL_LINE",
                    "Opening_Balances",
                    row,
                    "채권·채무 계정의 분개 방향과 금액을 확인해 주세요.",
                )
                continue
            if not isinstance(counterparty, str) or counterparty not in counterparties:
                issue(
                    "UNKNOWN_COUNTERPARTY", "Opening_Balances", row, "거래처 코드를 확인해 주세요."
                )
                continue
            key = (role, mapped, counterparty)
            opening[key] = opening.get(key, Decimal(0)) + amount

    if len(days) > 1:
        issue(
            "CUTOVER_DATE_MISMATCH", "Opening_Balances", "", "기초잔액 기준일을 하나로 맞춰 주세요."
        )
    as_of = next(iter(days)) if len(days) == 1 else None
    for role, section in (("AR", "AR_Opening"), ("AP", "AP_Opening")):
        rows = sorted({cell.row_key for cell in cells if cell.field_code.startswith(section + ".")})
        for row in rows:
            account = value(section, row, "account_code")
            counterparty = value(section, row, "counterparty_code")
            reference = value(section, row, "reference_code")
            amount = value(section, row, "original_amount")
            due = value(section, row, "due_date")
            if not all((account, counterparty, reference, amount, due)):
                issue("INCOMPLETE_OPEN_ITEM", section, row, "미결 항목의 필수 값을 입력해 주세요.")
                continue
            if row != f"{counterparty}|{reference}":
                issue(
                    "OPEN_ITEM_KEY_MISMATCH",
                    section,
                    row,
                    "거래처·원천 참조 행 키를 확인해 주세요.",
                )
                continue
            if len(row) > 300 or not isinstance(reference, str) or len(reference) > 100:
                issue("OPEN_ITEM_KEY_INVALID", section, row, "원천 참조 길이를 확인해 주세요.")
                continue
            if account != mappings.get(role):
                issue(
                    "CONTROL_ACCOUNT_MISMATCH",
                    section,
                    row,
                    "회사 채권·채무 역할 계정을 사용해 주세요.",
                )
                continue
            if counterparty not in counterparties:
                issue("UNKNOWN_COUNTERPARTY", section, row, "거래처 코드를 확인해 주세요.")
                continue
            if not isinstance(amount, Decimal) or amount <= 0 or not isinstance(due, date):
                issue("INVALID_OPEN_ITEM", section, row, "원금과 만기일을 확인해 주세요.")
                continue
            key = (role, str(account), str(counterparty))
            items[key] = items.get(key, Decimal(0)) + amount

    totals = tuple(
        PreviewTotal(*key, opening.get(key, Decimal(0)), items.get(key, Decimal(0)))
        for key in sorted(opening.keys() | items.keys())
    )
    for total in totals:
        if total.opening_amount != total.item_amount:
            issue(
                "OPEN_ITEM_TOTAL_MISMATCH",
                f"{total.role}_Opening",
                total.counterparty_code,
                "기초 전표와 미결 항목 합계가 다릅니다.",
            )
    return ArApPreview(version, digest({"cells": source}), as_of, not issues, tuple(issues), totals)
