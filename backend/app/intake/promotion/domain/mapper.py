"""검증된 원천 사실만 거래로 변환하며 이름 유사도나 AI 추측을 사용하지 않습니다."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.contracts.access_errors import InvalidInput, StateConflict
from app.intake.domain.canonical_fields import SourceType
from app.intake.domain.digest import digest
from app.intake.domain.validation import CanonicalRow
from app.intake.promotion.domain.errors import UnsupportedCurrency


@dataclass(frozen=True)
class TransactionFact:
    transaction_date: date
    accounting_date: date
    description: str
    amount: Decimal
    tax_amount: Decimal
    currency_code: str
    direction: str
    source_type: str
    source_id: str
    payment_method: str
    counterparty_code: str | None
    counterparty_text: bool
    fingerprint: str


def map_row(source: SourceType, row: CanonicalRow) -> TransactionFact:
    kinds = {
        SourceType.BANK_TRANSACTION: "BANK",
        SourceType.CARD_TRANSACTION: "CARD",
        SourceType.SALES: "SALES",
        SourceType.PURCHASE: "PURCHASE",
        SourceType.EXPENSE: "EXPENSE",
    }
    if source not in kinds:
        raise StateConflict()
    values = dict(row.values)
    try:
        occurred = date.fromisoformat(values["transaction_date"])
        accounting = date.fromisoformat(values.get("accounting_date") or values["transaction_date"])
        amount = Decimal(values["amount"])
        tax = Decimal(values.get("tax_amount") or "0")
    except (KeyError, ValueError, InvalidOperation):
        raise InvalidInput() from None
    if any(
        not v.is_finite() or abs(v) >= Decimal("1e15") or v != v.quantize(Decimal("0.0001"))
        for v in (amount, tax)
    ):
        raise InvalidInput()
    if values.get("currency") != "KRW":
        raise UnsupportedCurrency()
    if amount <= 0 or tax < 0 or tax > amount:
        raise InvalidInput()
    direction = values.get("direction") or (
        "IN"
        if source == SourceType.SALES
        else "OUT"
        if source != SourceType.BANK_TRANSACTION
        else ""
    )
    if direction not in {"IN", "OUT"} or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", row.source_id):
        raise InvalidInput()
    method = values.get("payment_method") or "UNSPECIFIED"
    if method not in {"BANK", "CARD", "CASH", "UNSPECIFIED"}:
        raise InvalidInput()
    code = values.get("counterparty_code") or None
    description = values.get("description") or "가져온 회계 자료"
    # Import ID와 표시용 거래처 이름은 경제적 원천 identity에 포함하지 않습니다.
    signature = digest(
        [
            "transaction-promotion-v1",
            kinds[source],
            row.source_id,
            occurred.isoformat(),
            accounting.isoformat(),
            format(amount, ".4f"),
            format(tax, ".4f"),
            "KRW",
            direction,
            method,
            code,
            description,
        ]
    )
    return TransactionFact(
        occurred,
        accounting,
        description,
        amount,
        tax,
        "KRW",
        "INFLOW" if direction == "IN" else "OUTFLOW",
        kinds[source],
        row.source_id,
        method,
        code,
        bool(values.get("counterparty")),
        signature,
    )
