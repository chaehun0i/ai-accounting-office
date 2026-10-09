"""MVP용 회계 템플릿입니다. 세법이나 법정 계정체계를 대체하지 않습니다."""

from datetime import date
from uuid import NAMESPACE_URL, uuid5

from app.accounting.templates.domain.entities import Template, TemplateAccount

DEFAULT_TEMPLATE = Template(
    id=uuid5(NAMESPACE_URL, "accounting:KR_STANDARD:1"),
    template_code="KR_STANDARD",
    name="기본 회계 계정과목",
    version=1,
    status="ACTIVE",
    valid_from=date(2026, 1, 1),
)
_ROWS = (
    ("1000", "자산", "ASSET", None, False, False),
    ("1010", "현금및현금성자산", "ASSET", "1000", True, False),
    ("1020", "보통예금", "ASSET", "1000", True, False),
    ("1100", "매출채권", "ASSET", "1000", True, False),
    ("1200", "부가세대급금", "ASSET", "1000", True, False),
    ("1300", "선급비용", "ASSET", "1000", True, False),
    ("1600", "유형자산", "ASSET", "1000", True, False),
    ("1690", "감가상각누계액", "ASSET", "1000", True, True),
    ("2000", "부채", "LIABILITY", None, False, False),
    ("2010", "매입채무", "LIABILITY", "2000", True, False),
    ("2020", "카드미지급금", "LIABILITY", "2000", True, False),
    ("2100", "부가세예수금", "LIABILITY", "2000", True, False),
    ("2200", "미지급비용", "LIABILITY", "2000", True, False),
    ("3000", "자본", "EQUITY", None, False, False),
    ("3010", "자본금", "EQUITY", "3000", True, False),
    ("4000", "수익", "REVENUE", None, False, False),
    ("4010", "매출", "REVENUE", "4000", True, False),
    ("4090", "기타수익", "REVENUE", "4000", True, False),
    ("5000", "비용", "EXPENSE", None, False, False),
    ("5010", "소프트웨어비", "EXPENSE", "5000", True, False),
    ("5020", "소모품비", "EXPENSE", "5000", True, False),
    ("5030", "임차료", "EXPENSE", "5000", True, False),
    ("5040", "지급수수료", "EXPENSE", "5000", True, False),
    ("5050", "급여", "EXPENSE", "5000", True, False),
    ("5060", "감가상각비", "EXPENSE", "5000", True, False),
)
DEFAULT_ACCOUNTS = tuple(
    TemplateAccount(
        id=uuid5(DEFAULT_TEMPLATE.id, code),
        coa_template_id=DEFAULT_TEMPLATE.id,
        account_code=code,
        account_name=name,
        account_type=kind,
        normal_balance="DEBIT" if ((kind in {"ASSET", "EXPENSE"}) != contra) else "CREDIT",
        parent_code=parent,
        posting_allowed=posting,
        is_contra=contra,
        display_order=index,
    )
    for index, (code, name, kind, parent, posting, contra) in enumerate(_ROWS)
)
