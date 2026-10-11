"""확정 원천 전표를 회사별 채권·채무로 인식합니다."""

import builtins
from collections.abc import Callable
from datetime import date
from uuid import UUID

from app.accounting.journals.application.posted_facts import posted_journal
from app.accounting.journals.domain.errors import AccountingError
from app.companies.application.service import require_company
from app.contracts.access_errors import ResourceNotFound
from app.finance.receivables.domain.entities import Obligation
from app.finance.settlements.application.contracts import FinanceUnitOfWork
from app.finance.settlements.application.policy import CONTROL_NAMES, permission, require_currency
from app.identity.users.domain.entities import Principal


class ObligationService:
    def __init__(self, factory: Callable[[], FinanceUnitOfWork]) -> None:
        self.factory = factory

    def list(
        self, actor: Principal, company: UUID, kind: str, as_of: date
    ) -> builtins.list[Obligation]:
        with self.factory() as uow:
            require_company(uow, actor, company, permission(kind))
            return uow.obligations(kind).list(company, as_of)

    def get(
        self, actor: Principal, company: UUID, kind: str, resource: UUID, as_of: date
    ) -> Obligation:
        with self.factory() as uow:
            require_company(uow, actor, company, permission(kind))
            value = uow.obligations(kind).get(company, resource, as_of)
            if value is None or value.origin_date > as_of:
                raise ResourceNotFound()
            return value

    def recognize(
        self, actor: Principal, company: UUID, kind: str, journal_id: UUID, due_date: date
    ) -> builtins.list[Obligation]:
        with self.factory() as uow:
            require_company(uow, actor, company, permission(kind, command=True))
            require_currency(uow, company)
            journal = posted_journal(uow, company, journal_id)
            if journal.reversal_of_id or due_date < journal.entry_date:
                raise AccountingError(
                    "BUSINESS_RULE_VIOLATION", "발생 전표와 지급기일을 확인해 주세요."
                )
            repo = uow.obligations(kind)
            result = []
            for line in journal.lines:
                account = uow.accounts.get(company_id=company, resource_id=line.account_id)
                assert account is not None
                amount = line.debit_amount if kind == "AR" else line.credit_amount
                if account.account_name not in CONTROL_NAMES[kind] or amount == 0:
                    continue
                if line.counterparty_id is None:
                    raise AccountingError(
                        "BUSINESS_RULE_VIOLATION", "채권·채무 분개에 거래처를 연결해 주세요."
                    )
                old = repo.origin(company, journal.id, line.line_no)
                if old:
                    if old.due_date != due_date:
                        raise AccountingError(
                            "IDEMPOTENCY_CONFLICT",
                            "이미 등록된 발생 전표의 지급기일이 다릅니다.",
                            409,
                        )
                    result.append(old)
                    continue
                resource = repo.add(
                    company,
                    journal.id,
                    line.line_no,
                    line.counterparty_id,
                    line.account_id,
                    amount,
                    due_date,
                )
                value = repo.get(company, resource, date.max)
                assert value is not None
                result.append(value)
            if not result:
                raise AccountingError(
                    "BUSINESS_RULE_VIOLATION", "선택한 전표에는 등록할 채권·채무 분개가 없습니다."
                )
            return result
