"""재무 명령의 권한·지원 통화·멱등 지문 공통 정책입니다."""

from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from app.accounting.journals.domain.errors import AccountingError
from app.contracts.access_errors import ResourceNotFound
from app.finance.settlements.application.contracts import FinanceUnitOfWork

CONTROL_NAMES = {"AR": {"매출채권"}, "AP": {"매입채무", "미지급금"}}


def permission(kind: str, *, command: bool = False) -> str:
    if kind not in CONTROL_NAMES:
        raise ResourceNotFound()
    return (
        ("collection.record" if kind == "AR" else "payment.record")
        if command
        else ("receivable.read" if kind == "AR" else "payable.read")
    )


def fingerprint(*parts: object) -> str:
    # 길이 접두사를 사용하여 구분 문자가 포함된 입력도 구별합니다.
    normalized = [format(part, ".4f") if isinstance(part, Decimal) else str(part) for part in parts]
    return sha256("".join(f"{len(part)}:{part}" for part in normalized).encode()).hexdigest()


def require_currency(uow: FinanceUnitOfWork, company: UUID) -> None:
    settings = uow.settings.get(company)
    if settings is None or settings.functional_currency_code != "KRW":
        raise AccountingError("FX_NOT_SUPPORTED", "현재 채권·채무 정산은 원화 회사만 지원합니다.")
