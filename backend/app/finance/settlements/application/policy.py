"""재무 명령의 권한·지원 통화·멱등 지문 공통 정책입니다."""

from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from app.accounting.journals.domain.errors import AccountingError
from app.accounting.templates.domain.defaults import (
    DEFAULT_ACCOUNTS,
    LEGACY_ACCOUNTS,
    PREVIOUS_ACCOUNTS,
)
from app.contracts.access_errors import ResourceNotFound
from app.finance.settlements.application.contracts import FinanceUnitOfWork

CONTROL_KINDS = {"AR", "AP"}
_CONTROL_CODES = {
    "AR": {"1100", "1101", "1110"},
    "AP": {"2010", "2011", "2030", "2040", "2390"},
}
_CASH_CODES = {"1010", "1020", "1030"}
_CONTROL_TEMPLATE_IDS = {
    kind: {
        row.id
        for row in (*LEGACY_ACCOUNTS, *PREVIOUS_ACCOUNTS, *DEFAULT_ACCOUNTS)
        if row.account_code in codes
    }
    for kind, codes in _CONTROL_CODES.items()
}
_CASH_TEMPLATE_IDS = {
    row.id
    for row in (*LEGACY_ACCOUNTS, *PREVIOUS_ACCOUNTS, *DEFAULT_ACCOUNTS)
    if row.account_code in _CASH_CODES
}


def control_account_ids(uow: FinanceUnitOfWork, company: UUID, kind: str) -> set[UUID]:
    mapping = uow.control_accounts.mapping(company, kind)
    if mapping is None:
        return set()
    return {mapping.account_id} | {
        account.id
        for account in uow.accounts.list(company)
        if account.template_account_id in _CONTROL_TEMPLATE_IDS[kind]
    }


def cash_account_ids(uow: FinanceUnitOfWork, company: UUID) -> set[UUID]:
    mapping = uow.control_accounts.mapping(company, "BANK_CASH")
    return ({mapping.account_id} if mapping else set()) | {
        account.id
        for account in uow.accounts.list(company)
        if account.template_account_id in _CASH_TEMPLATE_IDS
    }


def permission(kind: str, *, command: bool = False) -> str:
    if kind not in CONTROL_KINDS:
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
