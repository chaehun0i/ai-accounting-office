"""서버가 관리하는 기본 계정과목을 회사별 식별자로 준비합니다."""

from uuid import UUID, uuid4

from app.accounting.accounts.domain.entities import Account
from app.accounting.application.contracts import MasterUnitOfWork
from app.accounting.templates.domain.defaults import DEFAULT_ACCOUNTS


def prepare_accounts(uow: MasterUnitOfWork, company_id: UUID) -> int:
    """기존 계정과 전표 참조는 보존하고 누락된 기본 계정만 추가합니다."""
    known = {row.account_code: row.id for row in uow.accounts.list(company_id)}
    count = 0
    for row in DEFAULT_ACCOUNTS:
        if row.account_code in known:
            continue
        account_id = uuid4()
        uow.accounts.add(
            Account(
                id=account_id,
                company_id=company_id,
                template_account_id=row.id,
                account_code=row.account_code,
                account_name=row.account_name,
                account_type=row.account_type,
                normal_balance=row.normal_balance,
                posting_allowed=row.posting_allowed,
                is_contra=row.is_contra,
                parent_account_id=known.get(row.parent_code or ""),
                created_at=uow.now(),
                updated_at=uow.now(),
            )
        )
        known[row.account_code] = account_id
        count += 1
    return count
