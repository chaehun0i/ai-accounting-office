"""확정 원천 전표를 회사별 채권·채무로 인식합니다."""

import builtins
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.accounting.journals.application.posted_facts import posted_journal
from app.accounting.journals.domain.errors import AccountingError
from app.companies.application.service import require_company
from app.contracts.access_errors import ResourceNotFound
from app.finance.receivables.domain.entities import Obligation
from app.finance.settlements.application.contracts import FinanceUnitOfWork
from app.finance.settlements.application.policy import (
    control_account_ids,
    permission,
    require_currency,
)
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
            control_ids = control_account_ids(uow, company, kind)
            for line in journal.lines:
                account = uow.accounts.get(company_id=company, resource_id=line.account_id)
                assert account is not None
                amount = line.debit_amount if kind == "AR" else line.credit_amount
                if account.id not in control_ids or amount == 0:
                    continue
                if line.counterparty_id is None:
                    raise AccountingError(
                        "BUSINESS_RULE_VIOLATION", "채권·채무 분개에 거래처를 연결해 주세요."
                    )
                invoice = (
                    repo.invoice_source(company, journal.source_transaction_id)
                    if journal.source_transaction_id
                    else None
                )
                if invoice:
                    if (
                        invoice.account_id != line.account_id
                        or invoice.counterparty_id != line.counterparty_id
                        or invoice.original_amount != amount
                        or invoice.due_date != due_date
                        or (
                            invoice.origin_journal_id is not None
                            and (
                                invoice.origin_journal_id != journal.id
                                or invoice.origin_line_no != line.line_no
                            )
                        )
                    ):
                        raise AccountingError(
                            "IMPORT_SOURCE_CONFLICT",
                            "업무문서와 발생 전표가 일치하지 않습니다.",
                            409,
                        )
                    if invoice.origin_journal_id is None:
                        repo.attach_journal(company, invoice.id, journal.id, line.line_no)
                    attached = repo.get(company, invoice.id, date.max)
                    assert attached is not None
                    result.append(attached)
                    continue
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

    @staticmethod
    def recognize_invoice_in(
        uow: FinanceUnitOfWork,
        actor: Principal,
        company: UUID,
        kind: str,
        invoice: UUID,
        transaction: UUID,
        counterparty: UUID,
        amount: Decimal,
        due: date,
        recognized: date,
    ) -> UUID:
        """승인된 업무문서 명령의 동일 작업단위에서만 채권·채무를 인식합니다."""
        require_company(uow, actor, company, "invoice.approve")
        require_currency(uow, company)
        mapping = uow.control_accounts.mapping(company, kind)
        account = (
            uow.accounts.get(company_id=company, resource_id=mapping.account_id)
            if mapping is not None
            else None
        )
        if account is None or account.status != "ACTIVE" or not account.posting_allowed:
            raise AccountingError(
                "BUSINESS_RULE_VIOLATION", "회사 회계설정에서 채권·채무 계정을 확인해 주세요."
            )
        existing = uow.obligations(kind).invoice_source(company, transaction)
        if existing:
            if existing.source_invoice_id != invoice or existing.original_amount != amount:
                raise AccountingError("IMPORT_SOURCE_CONFLICT", "원천 업무문서가 다릅니다.", 409)
            return existing.id
        return uow.obligations(kind).add_invoice(
            company, invoice, transaction, counterparty, account.id, amount, due, recognized
        )

    @staticmethod
    def adjust_invoice_in(
        uow: FinanceUnitOfWork,
        actor: Principal,
        company: UUID,
        kind: str,
        target: UUID,
        note: UUID,
        note_type: str,
        amount: Decimal,
        effective: date,
    ) -> None:
        require_company(uow, actor, company, "invoice.approve")
        value = uow.obligations(kind).get(company, target, date.max, lock=True)
        if value is None:
            raise ResourceNotFound()
        if note_type == "CREDIT_NOTE" and amount > value.outstanding_amount:
            raise AccountingError(
                "CREDIT_NOTE_EXCEEDS_OPEN_AMOUNT", "감액할 수 있는 미정산 금액을 초과했습니다."
            )
        uow.obligations(kind).adjust(company, target, note, note_type, amount, effective)
