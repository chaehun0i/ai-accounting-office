"""매핑·검증·필드 안내가 공유하는 명시적 정본 필드입니다."""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class SourceType(StrEnum):
    BANK_TRANSACTION = "BANK_TRANSACTION"
    CARD_TRANSACTION = "CARD_TRANSACTION"
    SALES = "SALES"
    PURCHASE = "PURCHASE"
    EXPENSE = "EXPENSE"
    OPENING_BALANCE = "OPENING_BALANCE"
    COUNTERPARTY = "COUNTERPARTY"


class TargetContext(StrEnum):
    TRANSACTION_CANONICAL = "TRANSACTION_CANONICAL"
    ONBOARDING_DRAFT = "ONBOARDING_DRAFT"
    DOMAIN_MASTER = "DOMAIN_MASTER"


@dataclass(frozen=True)
class CanonicalField:
    code: str
    label: str
    kind: str
    required: bool = False
    aliases: tuple[str, ...] = ()


def normalize(value: str) -> str:
    return re.sub(r"[\s_\-]", "", unicodedata.normalize("NFKC", value)).casefold()


COMMON = (
    CanonicalField("source_id", "원본 자료 ID", "identifier", True, ("자료ID", "거래번호")),
    CanonicalField("transaction_date", "거래일", "date", True, ("거래일자", "date", "일자")),
    CanonicalField("amount", "금액", "decimal", True, ("합계금액", "거래금액")),
    CanonicalField("currency", "통화", "currency", True, ("통화코드", "currency_code")),
    CanonicalField("counterparty", "거래처", "text", False, ("거래처명",)),
    CanonicalField("description", "적요", "text", False, ("내용", "메모")),
    CanonicalField("direction", "입출금 구분", "direction", False, ("입출금",)),
    CanonicalField("tax_amount", "세액", "decimal", False, ("부가세",)),
    CanonicalField("payment_method", "결제수단", "payment_method"),
    CanonicalField("raw_reference", "원본 참조", "text"),
)
SCHEMAS: dict[SourceType, tuple[CanonicalField, ...]] = {
    kind: COMMON for kind in SourceType if kind != SourceType.COUNTERPARTY
}
SCHEMAS[SourceType.OPENING_BALANCE] = COMMON + (
    CanonicalField("account_code", "계정코드", "identifier", True, ("계정과목코드",)),
)
SCHEMAS[SourceType.COUNTERPARTY] = (
    COMMON[0],
    CanonicalField("display_name", "거래처명", "text", True, ("거래처",)),
    CanonicalField("legal_name", "법적 명칭", "text", False, ("상호",)),
    CanonicalField("business_number", "사업자번호", "business_number"),
    CanonicalField("role_code", "거래처 역할", "role", True, ("역할",)),
)


@dataclass(frozen=True)
class Mapping:
    sheet_index: int
    column_index: int
    canonical_field_code: str | None
    status: str


def suggest(source: SourceType, sheet_index: int, headers: tuple[str, ...]) -> list[Mapping]:
    result: list[Mapping] = []
    for index, header in enumerate(headers):
        matches = [
            field
            for field in SCHEMAS[source]
            if normalize(header)
            in {normalize(v) for v in (field.code, field.label, *field.aliases)}
        ]
        field = matches[0] if len(matches) == 1 else None
        status = "AMBIGUOUS" if len(matches) > 1 else "UNMAPPED"
        if field:
            status = "EXACT" if header == field.code else "ALIAS_MATCH"
        result.append(Mapping(sheet_index, index, field.code if field else None, status))
    codes = [m.canonical_field_code for m in result if m.canonical_field_code]
    return [
        Mapping(m.sheet_index, m.column_index, None, "AMBIGUOUS")
        if m.canonical_field_code and codes.count(m.canonical_field_code) > 1
        else m
        for m in result
    ]
