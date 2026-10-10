"""필수 입력·진행률·미지원 승격과 파생 금액을 결정론적으로 계산합니다."""

from dataclasses import dataclass, replace
from decimal import Decimal

from app.accounting.templates.domain.defaults import DEFAULT_ACCOUNTS
from app.onboarding.domain.catalog import (
    BY_CODE,
    CATALOG,
    FUTURE_SECTIONS,
    KEYS,
    REQUIRED_SECTIONS,
    SECTIONS,
)
from app.onboarding.domain.values import Cell, required


@dataclass(frozen=True)
class Issue:
    field_code: str | None
    row_key: str
    validation_code: str
    severity: str
    message: str


def validate(cells: list[Cell]) -> list[Issue]:
    issues: list[Issue] = []
    values = {(c.field_code, c.row_key): c for c in cells}
    for section in SECTIONS:
        rows = {
            c.row_key
            for c in cells
            if BY_CODE[c.field_code].section_code == section and c.source_type != "DERIVED"
        }
        if section in {"Company", "Accounting_Settings"}:
            rows.add("singleton")
        if section in REQUIRED_SECTIONS and section in KEYS and not rows:
            skipped = section == "Opening_Balances" and any(
                c.field_code == "Company.no_opening_balance" and c.value is True for c in cells
            )
            if not skipped:
                issues.append(
                    Issue(None, section, "REQUIRED_SECTION", "ERROR", "필수 항목을 입력해 주세요.")
                )
        for row in rows:
            for field in CATALOG:
                if (
                    field.section_code == section
                    and required(field, cells)
                    and (field.field_code, row) not in values
                ):
                    issues.append(
                        Issue(
                            field.field_code, row, "REQUIRED", "ERROR", "필수 값을 입력해 주세요."
                        )
                    )
        if section in FUTURE_SECTIONS and rows:
            issues.append(
                Issue(
                    None,
                    section,
                    "PENDING_DOMAIN_SUPPORT",
                    "ERROR",
                    "초안을 안전하게 보관했습니다. "
                    "이 항목의 회계정보 반영 기능이 준비되면 완료할 수 있습니다.",
                )
            )
    # 계정 유형과 정상 잔액의 불일치는 사용자가 검토할 수 있도록 차단합니다.
    for row in {c.row_key for c in cells if c.field_code.startswith("COA.")}:
        kind = values.get(("COA.account_type", row))
        balance = values.get(("COA.normal_balance", row))
        code = values.get(("COA.account_code", row))
        fixed = next(
            (
                account
                for account in DEFAULT_ACCOUNTS
                if code and account.account_code == str(code.value)
            ),
            None,
        )
        if (
            kind
            and balance
            and balance.value
            != (
                fixed.normal_balance
                if fixed and kind.value == fixed.account_type
                else "DEBIT"
                if kind.value in {"ASSET", "EXPENSE"}
                else "CREDIT"
            )
        ):
            issues.append(
                Issue(
                    "COA.normal_balance",
                    row,
                    "ACCOUNT_BALANCE_REVIEW",
                    "ERROR",
                    "차감 계정 등 별도 회계정책 확인이 필요합니다.",
                )
            )
    return issues


def progress(cells: list[Cell], section: str) -> tuple[int, int, str]:
    row_keys = {
        c.row_key
        for c in cells
        if BY_CODE[c.field_code].section_code == section and c.source_type != "DERIVED"
    }
    if section not in KEYS:
        row_keys.add("singleton")
    candidates = [
        (f, row)
        for f in CATALOG
        for row in row_keys
        if f.section_code == section
        and f.active
        and f.input_mode != "DERIVED_READONLY"
        and (f.required_rule_code != "CORPORATION" or required(f, cells))
    ]
    values = {(c.field_code, c.row_key): c for c in cells}
    # 시스템 기본값은 사용자가 입력해야 하는 분모에서 제외합니다.
    candidates = [
        (f, row)
        for f, row in candidates
        if not ((c := values.get((f.field_code, row))) and c.source_type == "SYSTEM_DEFAULT")
    ]
    complete = sum(
        1
        for f, row in candidates
        if (c := values.get((f.field_code, row))) is not None and c.status == "VALID"
    )
    warning = any(
        i
        for i in validate(cells)
        if (i.field_code and BY_CODE[i.field_code].section_code == section) or i.row_key == section
    )
    state = (
        "WARNING"
        if warning
        else "COMPLETE"
        if complete == len(candidates) and candidates
        else "IN_PROGRESS"
        if complete
        else "EMPTY"
    )
    return complete, len(candidates), state


def invalidate(cells: list[Cell], changed_sections: set[str]) -> list[Cell]:
    if changed_sections & {"Opening_Balances", "COA"}:
        return [replace(c, status="STALE") if c.source_type == "DERIVED" else c for c in cells]
    return cells


def recalculate(cells: list[Cell]) -> list[Cell]:
    debit = sum(
        (
            c.value
            for c in cells
            if c.field_code == "Opening_Balances.debit_amount" and isinstance(c.value, Decimal)
        ),
        Decimal(0),
    )
    credit = sum(
        (
            c.value
            for c in cells
            if c.field_code == "Opening_Balances.credit_amount" and isinstance(c.value, Decimal)
        ),
        Decimal(0),
    )
    result = [c for c in cells if c.source_type != "DERIVED"]
    for code, value in (
        ("debit_total", debit),
        ("credit_total", credit),
        ("balance_difference", debit - credit),
    ):
        result.append(Cell(f"Opening_Balances.{code}", "singleton", value, "DERIVED"))
    return result
