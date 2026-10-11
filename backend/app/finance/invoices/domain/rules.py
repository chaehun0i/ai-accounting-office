"""문서 금액과 정정 한도는 Decimal 사실만으로 판정합니다."""

from decimal import Decimal
from hashlib import sha256

from app.accounting.journals.domain.errors import AccountingError
from app.contracts.access_errors import InvalidInput, StateConflict
from app.core.values import require_money
from app.finance.invoices.domain.entities import Document, DocumentStatus, DocumentType


def validate_document(value: Document) -> None:
    if value.currency_code != "KRW":
        raise AccountingError("FX_NOT_SUPPORTED", "현재 업무문서는 원화만 지원합니다.")
    if (
        not 1 <= len(value.document_no.strip()) <= 100
        or not 1 <= len(value.source_system.strip()) <= 80
        or not 1 <= len(value.source_id.strip()) <= 100
        or value.version < 1
        or value.due_date < value.issue_date
        or not 1 <= len(value.lines) <= 500
        or [line.line_no for line in value.lines] != list(range(1, len(value.lines) + 1))
    ):
        raise InvalidInput()
    for line in value.lines:
        try:
            require_money(line.supply_amount)
            require_money(line.tax_amount)
            require_money(line.total_amount)
        except ValueError:
            raise AccountingError(
                "DOCUMENT_TOTAL_MISMATCH", "문서 항목의 금액을 확인해 주세요."
            ) from None
        amounts = (line.supply_amount, line.tax_amount, line.total_amount)
        if (
            not 1 <= len(line.description.strip()) <= 500
            or any(
                not amount.is_finite()
                or amount < 0
                or amount > 999999999999999
                or amount != amount.quantize(Decimal("0.0001"))
                for amount in amounts
            )
            or line.total_amount <= 0
        ):
            raise AccountingError("DOCUMENT_TOTAL_MISMATCH", "문서 항목의 금액을 확인해 주세요.")
        if (line.quantity is None) != (line.unit_price is None):
            raise InvalidInput()
        if line.quantity is not None and line.unit_price is not None:
            if (
                not line.quantity.is_finite()
                or not line.unit_price.is_finite()
                or line.quantity <= 0
                or line.unit_price < 0
                or line.quantity * line.unit_price != line.supply_amount
            ):
                raise AccountingError(
                    "DOCUMENT_TOTAL_MISMATCH", "수량과 단가의 곱이 공급가액과 다릅니다."
                )
    try:
        require_money(value.total_amount)
    except ValueError:
        raise AccountingError("DOCUMENT_TOTAL_MISMATCH", "문서 합계를 확인해 주세요.") from None
    if value.is_note:
        if (
            value.original_document_type
            not in {DocumentType.SALES_INVOICE, DocumentType.PURCHASE_INVOICE}
            or value.original_document_id is None
            or not value.reason_code
            or not 1 <= len(value.reason_code.strip()) <= 100
            or value.original_document_id == value.id
        ):
            raise InvalidInput()
    elif any((value.original_document_type, value.original_document_id, value.reason_code)):
        raise InvalidInput()


def document_fingerprint(value: Document) -> str:
    # 길이 접두사로 구분 문자 충돌을 막고 Decimal 표현 차이를 정규화합니다.
    parts: list[object] = [
        value.document_type,
        value.document_no,
        value.counterparty_id,
        value.issue_date,
        value.accounting_date,
        value.due_date,
        value.currency_code,
        value.source_system,
        value.source_id,
        value.original_document_type,
        value.original_document_id,
        value.reason_code,
        value.source_import_id,
        value.evidence_id,
    ]
    for line in value.lines:
        parts.extend(
            (
                line.line_no,
                line.description,
                format(line.supply_amount, ".4f"),
                format(line.tax_amount, ".4f"),
                format(line.quantity, ".4f") if line.quantity is not None else "",
                format(line.unit_price, ".4f") if line.unit_price is not None else "",
            )
        )
    return sha256("".join(f"{len(str(part))}:{part}" for part in parts).encode()).hexdigest()


def require_transition(value: Document, action: str) -> DocumentStatus:
    if action == "submit" and value.status == DocumentStatus.DRAFT:
        return DocumentStatus.REVIEW_REQUIRED
    if action == "approve" and value.status == DocumentStatus.REVIEW_REQUIRED:
        return DocumentStatus.APPLIED if value.is_note else DocumentStatus.APPROVED
    raise StateConflict()


def correction_outstanding(
    original: Decimal, allocated: Decimal, credits: Decimal, debits: Decimal
) -> Decimal:
    """원금·확정 배분·승인 정정 사실을 보존한 채 잔액을 재현합니다."""
    for amount in (original, allocated, credits, debits):
        try:
            require_money(amount)
        except ValueError:
            raise InvalidInput() from None
        if amount < 0:
            raise InvalidInput()
    remaining = original + debits - credits - allocated
    if remaining < 0:
        raise AccountingError(
            "CREDIT_NOTE_EXCEEDS_OPEN_AMOUNT", "감액할 수 있는 미정산 금액을 초과했습니다."
        )
    require_money(remaining)
    return remaining


def validate_correction(original: Document, note: Document, outstanding: Decimal) -> None:
    validate_document(note)
    if (
        original.is_note
        or original.status != DocumentStatus.APPROVED
        or note.original_document_id != original.id
        or note.original_document_type != original.document_type
        or note.company_id != original.company_id
        or note.counterparty_id != original.counterparty_id
        or note.accounting_date < original.accounting_date
        or note.currency_code != original.currency_code
    ):
        raise InvalidInput()
    if note.document_type == DocumentType.CREDIT_NOTE:
        if outstanding == 0:
            raise AccountingError(
                "INVOICE_ALREADY_SETTLED", "정산이 끝난 문서의 환불은 별도 업무가 필요합니다.", 409
            )
        if note.total_amount > outstanding:
            raise AccountingError(
                "CREDIT_NOTE_EXCEEDS_OPEN_AMOUNT", "감액할 수 있는 미정산 금액을 초과했습니다."
            )
