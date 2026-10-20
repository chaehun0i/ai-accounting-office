"""온보딩 완료 전에 Opening 원천을 기존 승격 규칙과 대조합니다."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.accounting.opening_balances.application.ar_ap_preview import preview_ar_ap
from app.onboarding.application.contracts import OnboardingUnitOfWork
from app.onboarding.domain.validation import Issue
from app.onboarding.domain.values import Cell


def cutover_issues(
    uow: OnboardingUnitOfWork, company: UUID, cells: list[Cell], version: int
) -> list[Issue]:
    values = {(cell.field_code, cell.row_key): cell.value for cell in cells}
    rows = sorted(
        {
            cell.row_key
            for cell in cells
            if cell.field_code.startswith("Opening_Balances.") and cell.source_type != "DERIVED"
        }
    )
    has_items = any(cell.field_code.startswith(("AR_Opening.", "AP_Opening.")) for cell in cells)
    if not rows and not has_items:
        return []
    issues: list[Issue] = []

    def add(field: str | None, row: str, code: str, message: str) -> None:
        issues.append(Issue(field, row, code, "ERROR", message))

    if values.get(("Company.no_opening_balance", "singleton")) is True:
        add(
            "Company.no_opening_balance",
            "singleton",
            "OPENING_SOURCE_CONFLICT",
            "기초잔액 없음 선택과 입력된 기초자료가 충돌합니다.",
        )
    canonical = uow.accounts.list(company)
    valid_accounts = {
        account.account_code
        for account in canonical
        if account.status == "ACTIVE" and account.posting_allowed
    }
    if not canonical:
        valid_accounts = {
            str(cell.value)
            for cell in cells
            if cell.field_code == "COA.account_code"
            and values.get(("COA.posting_allowed", cell.row_key)) is True
        }
    account_codes = {account.id: account.account_code for account in canonical}
    mappings = {
        role: account_codes[mapping.account_id]
        for role in ("AR", "AP")
        if (mapping := uow.control_accounts.mapping(company, role)) is not None
        and mapping.account_id in account_codes
    }
    source_codes = {
        str(cell.value)
        for cell in cells
        if cell.field_code.endswith(".counterparty_code")
        and cell.field_code.split(".", 1)[0] in ("Opening_Balances", "AR_Opening", "AP_Opening")
    }
    draft_codes = {
        str(cell.value) for cell in cells if cell.field_code == "Counterparties.counterparty_code"
    }
    counterparties = draft_codes | {
        code
        for code in source_codes
        if (cp := uow.counterparties.by_code(company_id=company, code=code)) is not None
        and cp.status == "ACTIVE"
    }
    days: set[date] = set()
    debit_total = Decimal(0)
    credit_total = Decimal(0)
    for row in rows:
        day = values.get(("Opening_Balances.as_of_date", row))
        account = values.get(("Opening_Balances.account_code", row))
        debit = values.get(("Opening_Balances.debit_amount", row))
        credit = values.get(("Opening_Balances.credit_amount", row))
        currency = values.get(("Opening_Balances.currency_code", row))
        counterparty = values.get(("Opening_Balances.counterparty_code", row))
        if not isinstance(day, date):
            add(
                "Opening_Balances.as_of_date",
                row,
                "INVALID_CUTOVER_DATE",
                "기준일을 확인해 주세요.",
            )
        else:
            days.add(day)
        if account not in valid_accounts:
            add(
                "Opening_Balances.account_code",
                row,
                "UNKNOWN_ACCOUNT",
                "전기 가능한 계정을 선택해 주세요.",
            )
        if currency not in (None, "KRW"):
            add(
                "Opening_Balances.currency_code",
                row,
                "FX_NOT_SUPPORTED",
                "원화 기초잔액만 지원합니다.",
            )
        if counterparty and counterparty not in counterparties:
            add(
                "Opening_Balances.counterparty_code",
                row,
                "UNKNOWN_COUNTERPARTY",
                "거래처 코드를 확인해 주세요.",
            )
        if (
            not isinstance(debit, Decimal)
            or not isinstance(credit, Decimal)
            or not ((debit > 0 and credit == 0) or (credit > 0 and debit == 0))
        ):
            add(
                "Opening_Balances.debit_amount",
                row,
                "INVALID_OPENING_AMOUNT",
                "차변 또는 대변 한쪽에 양수를 입력해 주세요.",
            )
        else:
            debit_total += debit
            credit_total += credit
    if len(days) > 1:
        add(
            "Opening_Balances.as_of_date",
            "Opening_Balances",
            "CUTOVER_DATE_MISMATCH",
            "기준일을 하나로 맞춰 주세요.",
        )
    if rows and debit_total != credit_total:
        add(
            "Opening_Balances.debit_amount",
            "Opening_Balances",
            "OPENING_NOT_BALANCED",
            "기초잔액 차변·대변 합계가 다릅니다.",
        )
    preview = preview_ar_ap(cells, version, mappings, counterparties)
    for item in preview.issues:
        field = {
            "INVALID_CONTROL_LINE": "debit_amount",
            "UNKNOWN_COUNTERPARTY": "counterparty_code",
            "CONTROL_ACCOUNT_MISMATCH": "account_code",
            "OPEN_ITEM_TOTAL_MISMATCH": "original_amount",
            "INVALID_OPEN_ITEM": "original_amount",
            "INCOMPLETE_OPEN_ITEM": "reference_code",
            "OPEN_ITEM_KEY_MISMATCH": "reference_code",
            "OPEN_ITEM_KEY_INVALID": "reference_code",
            "INVALID_CUTOVER_DATE": "as_of_date",
            "CUTOVER_DATE_MISMATCH": "as_of_date",
        }.get(item.code)
        code = (
            f"{item.section}.{field}"
            if field and item.section in ("Opening_Balances", "AR_Opening", "AP_Opening")
            else None
        )
        add(code, item.row_key or item.section, item.code, item.message)
    return issues
