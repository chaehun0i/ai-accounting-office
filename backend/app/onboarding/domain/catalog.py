"""화면·양식·검증·DB 등록이 함께 사용하는 단일 필드 카탈로그입니다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    field_code: str
    section_code: str
    label: str
    data_type: str = "TEXT"
    input_mode: str = "TEXT"
    required_rule_code: str = "ALWAYS"
    enum_source_code: str | None = None
    derived_handler_key: str | None = None
    display_order: int = 0
    active: bool = True


SECTIONS = {
    "Company": "회사 기본정보",
    "Accounting_Settings": "회계설정",
    "COA": "계정과목",
    "Counterparties": "거래처",
    "Bank_Accounts": "은행",
    "Card_Accounts": "카드",
    "Opening_Balances": "기초잔액",
    "Fixed_Assets": "고정자산",
    "Inventory_Items": "재고 품목",
    "Opening_Inventory": "기초 재고",
    "AR_Opening": "기초 매출채권",
    "AP_Opening": "기초 매입채무",
}
ENUMS: dict[str, tuple[str, ...]] = {
    "taxpayer_type": ("CORPORATION", "SOLE_PROPRIETOR"),
    "functional_currency_code": ("KRW",),
    "currency_code": ("KRW",),
    "account_type": ("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"),
    "normal_balance": ("DEBIT", "CREDIT"),
    "counterparty_type": ("CORPORATION", "INDIVIDUAL", "SOLE_PROPRIETOR", "GOVERNMENT", "OTHER"),
    "accounting_framework_code": ("K_GAAP", "K_IFRS"),
    "reporting_taxonomy_code": ("STANDARD",),
    "timezone": ("Asia/Seoul",),
    "depreciation_method": ("STRAIGHT_LINE",),
    "cost_method": ("FIFO", "WEIGHTED_AVERAGE"),
}
KEYS: dict[str, tuple[str, ...]] = {
    "COA": ("account_code",),
    "Counterparties": ("counterparty_code",),
    "Bank_Accounts": ("bank_account_code",),
    "Card_Accounts": ("card_account_code",),
    "Fixed_Assets": ("asset_code",),
    "Inventory_Items": ("item_code",),
    "Opening_Balances": ("as_of_date", "account_code", "counterparty_code"),
    "Opening_Inventory": ("as_of_date", "item_code"),
    "AR_Opening": ("counterparty_code", "reference_code"),
    "AP_Opening": ("counterparty_code", "reference_code"),
}
FUTURE_SECTIONS = frozenset(KEYS) - {"COA", "Counterparties"}
REQUIRED_SECTIONS = frozenset({"Company", "Accounting_Settings", "COA", "Opening_Balances"})


def fields(section: str, specs: list[tuple[str, str, str, str]]) -> tuple[Field, ...]:
    return tuple(
        Field(
            f"{section}.{code}",
            section,
            label,
            kind,
            "LOOKUP"
            if code in ENUMS
            else {"NUMERIC": "NUMBER", "BOOLEAN": "BOOLEAN", "DATE": "DATE"}.get(kind, "TEXT"),
            rule,
            code if code in ENUMS else None,
            display_order=i,
        )
        for i, (code, label, kind, rule) in enumerate(specs)
    )


CATALOG = (
    *fields(
        "Company",
        [
            ("company_name", "회사명", "TEXT", "ALWAYS"),
            ("business_number", "사업자등록번호", "TEXT", "ALWAYS"),
            ("corporation_number", "법인등록번호", "TEXT", "CORPORATION"),
            ("taxpayer_type", "사업자 유형", "TEXT", "ALWAYS"),
            ("opening_date", "개업일", "DATE", "ALWAYS"),
            ("timezone", "시간대", "TEXT", "ALWAYS"),
        ],
    ),
    *fields(
        "Accounting_Settings",
        [
            ("functional_currency_code", "기능통화", "TEXT", "ALWAYS"),
            ("fiscal_year_start_month", "회계연도 시작 월", "NUMERIC", "ALWAYS"),
            ("accounting_framework_code", "회계기준", "TEXT", "ALWAYS"),
            ("reporting_taxonomy_code", "보고 분류", "TEXT", "ALWAYS"),
            ("journal_number_prefix", "전표번호 접두어", "TEXT", "ALWAYS"),
        ],
    ),
    *fields(
        "COA",
        [
            ("account_code", "계정 코드", "TEXT", "ALWAYS"),
            ("account_name", "계정명", "TEXT", "ALWAYS"),
            ("account_type", "계정 유형", "TEXT", "ALWAYS"),
            ("normal_balance", "정상 잔액", "TEXT", "ALWAYS"),
            ("posting_allowed", "전기 허용", "BOOLEAN", "ALWAYS"),
        ],
    ),
    *fields(
        "Counterparties",
        [
            ("counterparty_code", "거래처 코드", "TEXT", "ALWAYS"),
            ("legal_name", "거래처 정식명", "TEXT", "ALWAYS"),
            ("business_number", "사업자등록번호", "TEXT", "NEVER"),
            ("counterparty_type", "거래처 유형", "TEXT", "ALWAYS"),
            ("payment_term_code", "지급조건 코드", "TEXT", "NEVER"),
        ],
    ),
    *fields(
        "Opening_Balances",
        [
            ("as_of_date", "기준일", "DATE", "ALWAYS"),
            ("account_code", "계정 코드", "TEXT", "ALWAYS"),
            ("debit_amount", "차변 금액", "NUMERIC", "ALWAYS"),
            ("credit_amount", "대변 금액", "NUMERIC", "ALWAYS"),
            ("counterparty_code", "거래처 코드", "TEXT", "NEVER"),
            ("currency_code", "통화", "TEXT", "NEVER"),
        ],
    ),
    *fields(
        "Fixed_Assets",
        [
            ("asset_code", "자산 코드", "TEXT", "ALWAYS"),
            ("asset_name", "자산명", "TEXT", "ALWAYS"),
            ("acquisition_date", "취득일", "DATE", "ALWAYS"),
            ("acquisition_cost", "취득원가", "NUMERIC", "ALWAYS"),
            ("useful_life_months", "내용연수 개월", "NUMERIC", "ALWAYS"),
            ("depreciation_method", "감가상각 방법", "TEXT", "ALWAYS"),
        ],
    ),
    *fields(
        "Inventory_Items",
        [
            ("item_code", "품목 코드", "TEXT", "ALWAYS"),
            ("item_name", "품목명", "TEXT", "ALWAYS"),
            ("unit_of_measure", "단위", "TEXT", "ALWAYS"),
            ("cost_method", "원가 방법", "TEXT", "ALWAYS"),
            ("opening_quantity", "기초 수량", "NUMERIC", "NEVER"),
            ("opening_unit_cost", "기초 단가", "NUMERIC", "NEVER"),
        ],
    ),
    *fields(
        "Opening_Inventory",
        [
            ("as_of_date", "기준일", "DATE", "ALWAYS"),
            ("item_code", "품목 코드", "TEXT", "ALWAYS"),
            ("opening_quantity", "기초 수량", "NUMERIC", "ALWAYS"),
            ("opening_unit_cost", "기초 단가", "NUMERIC", "ALWAYS"),
        ],
    ),
    *tuple(
        f
        for section, code in (
            ("Bank_Accounts", "bank_account_code"),
            ("Card_Accounts", "card_account_code"),
        )
        for f in fields(
            section,
            [
                (code, "관리 코드", "TEXT", "ALWAYS"),
                ("alias", "별칭", "TEXT", "ALWAYS"),
                ("provider_code", "금융기관 코드", "TEXT", "ALWAYS"),
                ("currency_code", "통화", "TEXT", "ALWAYS"),
                ("external_reference", "외부 보관소 참조", "TEXT", "NEVER"),
            ],
        )
    ),
    *tuple(
        f
        for section in ("AR_Opening", "AP_Opening")
        for f in fields(
            section,
            [
                ("counterparty_code", "거래처 코드", "TEXT", "ALWAYS"),
                ("reference_code", "원천 참조", "TEXT", "ALWAYS"),
                ("original_amount", "원금", "NUMERIC", "ALWAYS"),
                ("due_date", "만기일", "DATE", "ALWAYS"),
                ("account_code", "계정 코드", "TEXT", "ALWAYS"),
            ],
        )
    ),
    Field(
        "Company.no_opening_balance",
        "Company",
        "기초잔액이 없는 신규 회사입니다",
        "BOOLEAN",
        "BOOLEAN",
        "NEVER",
        display_order=99,
    ),
    Field(
        "Opening_Balances.debit_total",
        "Opening_Balances",
        "차변 합계",
        "NUMERIC",
        "DERIVED_READONLY",
        "NEVER",
        derived_handler_key="debit_total",
        display_order=100,
    ),
    Field(
        "Opening_Balances.credit_total",
        "Opening_Balances",
        "대변 합계",
        "NUMERIC",
        "DERIVED_READONLY",
        "NEVER",
        derived_handler_key="credit_total",
        display_order=101,
    ),
    Field(
        "Opening_Balances.balance_difference",
        "Opening_Balances",
        "차대 차이",
        "NUMERIC",
        "DERIVED_READONLY",
        "NEVER",
        derived_handler_key="balance_difference",
        display_order=102,
    ),
)
BY_CODE = {f.field_code: f for f in CATALOG}
