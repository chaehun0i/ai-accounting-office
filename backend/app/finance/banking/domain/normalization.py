"""확정된 공통 Intake 행을 은행/카드 사실로 변환합니다."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.contracts.access_errors import InvalidInput
from app.core.values import require_money
from app.finance.banking.domain.entities import FinancialSource
from app.finance.cards.domain.rules import direction_for, normalize_status
from app.finance.reconciliation.domain.rules import money, source_fingerprint
from app.intake.domain.entities import Import, Receipt
from app.intake.domain.validation import CanonicalRow


def financial_text(value: str, maximum: int) -> str:
    value = value.strip()
    # 원 계좌·카드번호를 별칭/메모에 우회 저장하지 않습니다.
    if len(value) > maximum or re.search(r"(?:\d[ -]?){10,}", value):
        raise InvalidInput()
    return value


def normalize_row(
    source: Import,
    receipt: Receipt,
    row: CanonicalRow,
    account_id: UUID,
    kind: str,
    statement_id: UUID | None,
) -> FinancialSource:
    values = dict(row.values)
    if values.get("currency") != "KRW":
        raise InvalidInput()
    amount = money(Decimal(values["amount"]))
    status = (
        normalize_status(values.get("source_status", "CAPTURED")) if kind == "CARD" else "CAPTURED"
    )
    direction = direction_for(status) if kind == "CARD" else values.get("direction", "")
    if direction not in {"IN", "OUT"}:
        raise InvalidInput()
    if kind == "CARD" and values.get("direction", direction) != direction:
        raise InvalidInput()
    occurred = datetime.combine(
        date.fromisoformat(values["transaction_date"]), datetime.min.time(), UTC
    )
    balance = (
        require_money(Decimal(values["balance_after"])) if values.get("balance_after") else None
    )
    reference = financial_text(values.get("raw_reference", ""), 100)
    party = financial_text(values.get("counterparty", ""), 200)
    description = financial_text(values.get("description", ""), 500)
    fingerprint = source_fingerprint(
        [
            kind,
            occurred.isoformat(),
            direction,
            format(amount, "f"),
            status,
            reference,
            party,
            description,
            str(balance),
            "KRW",
        ]
    )
    return FinancialSource(
        id=uuid4(),
        company_id=source.company_id,
        account_id=account_id,
        kind=kind,
        source_system=source.source_system,
        source_id=row.source_id,
        source_fingerprint=fingerprint,
        occurred_at=occurred,
        direction=direction,
        amount=amount,
        counterparty_text=party,
        description=description,
        reference=reference,
        source_status=status,
        balance_after=balance,
        source_import_id=source.id,
        source_receipt_id=receipt.id,
        sheet_index=row.sheet_index,
        row_number=row.row_number,
        statement_id=statement_id,
    )
