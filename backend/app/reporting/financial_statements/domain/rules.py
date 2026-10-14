"""재무제표 숫자는 조정 시산표의 Decimal 사실에서만 결정합니다."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.accounting.ledger.domain.entities import TrialRow
from app.contracts.errors import ApplicationError

ZERO = Decimal("0")


class ReportMappingIncomplete(ApplicationError):
    code = "REPORT_MAPPING_INCOMPLETE"
    status_code = 422
    message = "사용된 계정과목의 재무제표 매핑이 없습니다."


class ReportMappingDuplicated(ApplicationError):
    code = "REPORT_MAPPING_DUPLICATED"
    status_code = 422
    message = "계정과목에 중복된 재무제표 매핑이 있습니다."


class BalanceSheetUnbalanced(ApplicationError):
    code = "BALANCE_SHEET_UNBALANCED"
    status_code = 422
    message = "재무상태표 자산과 부채·자본 합계가 일치하지 않습니다."


class ReportSourceStale(ApplicationError):
    code = "REPORT_SOURCE_STALE"
    status_code = 409
    message = "마감 장부 기준이 변경되었습니다. 새 마감 결과로 다시 생성해 주세요."


class ReportIdempotencyConflict(ApplicationError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409
    message = "같은 멱등성 키로 다른 재무제표 생성을 요청할 수 없습니다."


@dataclass(frozen=True)
class LineDefinition:
    statement_type: str
    line_code: str
    label: str
    parent_code: str | None
    display_order: int
    normal_sign: str
    subtotal_type: str


LINES = (
    LineDefinition("BALANCE_SHEET", "ASSETS", "자산총계", None, 10, "DEBIT", "TOTAL"),
    LineDefinition("BALANCE_SHEET", "ASSET_ACCOUNTS", "자산", "ASSETS", 11, "DEBIT", "LEAF"),
    LineDefinition("BALANCE_SHEET", "LIABILITIES", "부채총계", None, 20, "CREDIT", "TOTAL"),
    LineDefinition(
        "BALANCE_SHEET", "LIABILITY_ACCOUNTS", "부채", "LIABILITIES", 21, "CREDIT", "LEAF"
    ),
    LineDefinition("BALANCE_SHEET", "EQUITY", "자본총계", None, 30, "CREDIT", "TOTAL"),
    LineDefinition("BALANCE_SHEET", "EQUITY_ACCOUNTS", "자본", "EQUITY", 31, "CREDIT", "LEAF"),
    LineDefinition(
        "BALANCE_SHEET",
        "UNTRANSFERRED_PROFIT",
        "미대체 누적손익",
        "EQUITY",
        32,
        "CREDIT",
        "DERIVED",
    ),
    LineDefinition(
        "BALANCE_SHEET", "LIABILITIES_EQUITY", "부채와 자본총계", None, 40, "CREDIT", "TOTAL"
    ),
    LineDefinition("INCOME_STATEMENT", "REVENUE", "매출액", None, 10, "CREDIT", "LEAF"),
    LineDefinition("INCOME_STATEMENT", "COGS", "매출원가", None, 20, "DEBIT", "LEAF"),
    LineDefinition("INCOME_STATEMENT", "GROSS_PROFIT", "매출총이익", None, 30, "CREDIT", "TOTAL"),
    LineDefinition("INCOME_STATEMENT", "OPERATING_EXPENSE", "영업비용", None, 40, "DEBIT", "LEAF"),
    LineDefinition("INCOME_STATEMENT", "OPERATING_PROFIT", "영업이익", None, 50, "CREDIT", "TOTAL"),
    LineDefinition(
        "INCOME_STATEMENT", "NON_OPERATING_INCOME", "영업외수익", None, 60, "CREDIT", "LEAF"
    ),
    LineDefinition(
        "INCOME_STATEMENT", "NON_OPERATING_EXPENSE", "영업외비용", None, 70, "DEBIT", "LEAF"
    ),
    LineDefinition(
        "INCOME_STATEMENT", "PROFIT_BEFORE_TAX", "법인세차감전이익", None, 80, "CREDIT", "TOTAL"
    ),
    LineDefinition("INCOME_STATEMENT", "TAX_EXPENSE", "법인세비용", None, 90, "DEBIT", "LEAF"),
    LineDefinition("INCOME_STATEMENT", "NET_PROFIT", "당기순이익", None, 100, "CREDIT", "TOTAL"),
)
LINE_BY_CODE = {line.line_code: line for line in LINES}
LEAF_BY_TYPE = {
    "ASSET": {"ASSET_ACCOUNTS"},
    "LIABILITY": {"LIABILITY_ACCOUNTS"},
    "EQUITY": {"EQUITY_ACCOUNTS"},
    "REVENUE": {"REVENUE", "NON_OPERATING_INCOME"},
    "EXPENSE": {"COGS", "OPERATING_EXPENSE", "NON_OPERATING_EXPENSE", "TAX_EXPENSE"},
}
COGS_CODES = {"5300", "5310", "5320", "5400", "5410", "5420"}
NON_OPERATING_REVENUE_CODES = {
    "4090",
    *(f"{code:04d}" for code in range(4050, 4090, 10)),
    *(f"{code:04d}" for code in range(4100, 4230, 10)),
}
NON_OPERATING_EXPENSE_CODES = {
    "5500",
    "5510",
    "5520",
    "5530",
    "5540",
    "5550",
    "5560",
    "5570",
    "5580",
    "5590",
    "5610",
    "5620",
    "5640",
}
TAX_CODES = {"5600", "5630"}


def default_line(account_type: str, template_code: str) -> str:
    """기본 KR template의 안정적인 코드만 분류하며 계정명 추측은 하지 않습니다."""
    if account_type == "ASSET":
        return "ASSET_ACCOUNTS"
    if account_type == "LIABILITY":
        return "LIABILITY_ACCOUNTS"
    if account_type == "EQUITY":
        return "EQUITY_ACCOUNTS"
    if account_type == "REVENUE":
        return "NON_OPERATING_INCOME" if template_code in NON_OPERATING_REVENUE_CODES else "REVENUE"
    if account_type == "EXPENSE":
        if template_code in COGS_CODES:
            return "COGS"
        if template_code in TAX_CODES:
            return "TAX_EXPENSE"
        if template_code in NON_OPERATING_EXPENSE_CODES:
            return "NON_OPERATING_EXPENSE"
        return "OPERATING_EXPENSE"
    raise ReportMappingIncomplete()


def calculate(
    rows: list[TrialRow], mappings: list[tuple[UUID, str]], account_types: dict[UUID, str]
) -> dict[str, Decimal]:
    """IS는 당월 movement, BS는 마감일 ending; 미대체 누적손익을 별도 표시합니다."""
    by_account: dict[UUID, str] = {}
    for account_id, code in mappings:
        kind = account_types.get(account_id)
        if kind is None or code not in LEAF_BY_TYPE.get(kind, set()):
            raise ReportMappingIncomplete()
        if account_id in by_account:
            raise ReportMappingDuplicated()
        by_account[account_id] = code
    result = {line.line_code: ZERO for line in LINES}
    cumulative_profit = ZERO
    for row in rows:
        if not any((row.opening_debit, row.opening_credit, row.period_debit, row.period_credit)):
            continue
        mapped_code = by_account.get(row.account_id)
        if mapped_code is None:
            raise ReportMappingIncomplete()
        definition = LINE_BY_CODE[mapped_code]
        if definition.normal_sign == "DEBIT":
            ending = row.ending_debit - row.ending_credit
            movement = row.period_debit - row.period_credit
        else:
            ending = row.ending_credit - row.ending_debit
            movement = row.period_credit - row.period_debit
        result[mapped_code] += ending if definition.statement_type == "BALANCE_SHEET" else movement
        if account_types[row.account_id] == "REVENUE":
            cumulative_profit += row.ending_credit - row.ending_debit
        elif account_types[row.account_id] == "EXPENSE":
            cumulative_profit -= row.ending_debit - row.ending_credit
    result["ASSETS"] = result["ASSET_ACCOUNTS"]
    result["LIABILITIES"] = result["LIABILITY_ACCOUNTS"]
    result["UNTRANSFERRED_PROFIT"] = cumulative_profit
    result["EQUITY"] = result["EQUITY_ACCOUNTS"] + cumulative_profit
    result["LIABILITIES_EQUITY"] = result["LIABILITIES"] + result["EQUITY"]
    result["GROSS_PROFIT"] = result["REVENUE"] - result["COGS"]
    result["OPERATING_PROFIT"] = result["GROSS_PROFIT"] - result["OPERATING_EXPENSE"]
    result["PROFIT_BEFORE_TAX"] = (
        result["OPERATING_PROFIT"]
        + result["NON_OPERATING_INCOME"]
        - result["NON_OPERATING_EXPENSE"]
    )
    result["NET_PROFIT"] = result["PROFIT_BEFORE_TAX"] - result["TAX_EXPENSE"]
    if result["ASSETS"] != result["LIABILITIES_EQUITY"]:
        raise BalanceSheetUnbalanced()
    return result
