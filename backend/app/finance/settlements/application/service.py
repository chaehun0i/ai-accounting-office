"""확정 전표를 근거로 채권채무와 배분 사실을 관리합니다."""

import builtins
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.accounting.journals.application.posted_facts import posted_journal
from app.accounting.journals.domain.errors import AccountingError
from app.companies.application.service import require_company
from app.contracts.access_errors import ResourceNotFound
from app.finance.receivables.application.service import ObligationService
from app.finance.settlements.application.contracts import FinanceUnitOfWork
from app.finance.settlements.application.policy import (
    CONTROL_NAMES,
    fingerprint,
    permission,
    require_currency,
)
from app.finance.settlements.domain.entities import Allocation, Settlement
from app.finance.settlements.domain.rules import check_version, positive
from app.identity.users.domain.entities import Principal


class FinanceService(ObligationService):
    def __init__(self, factory: Callable[[], FinanceUnitOfWork]) -> None:
        self.factory = factory

    def settlements(
        self, actor: Principal, company: UUID, kind: str, target: UUID | None = None
    ) -> builtins.list[Settlement]:
        with self.factory() as uow:
            require_company(uow, actor, company, permission(kind))
            if target and uow.obligations(kind).get(company, target, date.max) is None:
                raise ResourceNotFound()
            return uow.settlements(kind).list(company, target)

    def create(
        self,
        actor: Principal,
        company: UUID,
        kind: str,
        journal_id: UUID,
        settlement_date: date,
        total_amount: Decimal,
        method: str,
        reference_no: str,
        key: str,
    ) -> Settlement:
        positive(total_amount)
        if method not in {"BANK_TRANSFER", "CASH", "OTHER"}:
            raise AccountingError("BUSINESS_RULE_VIOLATION", "수금·지급 방법을 확인해 주세요.")
        command = f"{kind}_CREATE"
        digest = fingerprint(journal_id, settlement_date, total_amount, method, reference_no)
        with self.factory() as uow:
            require_company(uow, actor, company, permission(kind, command=True))
            require_currency(uow, company)
            uow.lock_command(company, actor.user_id, command, key)
            repo = uow.settlements(kind)
            replay = repo.replay(company, actor.user_id, command, key, digest)
            if replay:
                value = repo.get(company, replay)
                assert value is not None
                return value
            journal = posted_journal(uow, company, journal_id)
            if journal.entry_date != settlement_date or journal.reversal_of_id:
                raise AccountingError(
                    "BUSINESS_RULE_VIOLATION", "수금·지급 전표와 일자를 확인해 주세요."
                )
            if repo.origin(company, journal_id):
                raise AccountingError(
                    "IDEMPOTENCY_CONFLICT", "이미 등록한 수금·지급 전표입니다.", 409
                )
            value = Settlement(
                id=uuid4(),
                company_id=company,
                journal_entry_id=journal_id,
                settlement_date=settlement_date,
                total_amount=total_amount,
                currency_code="KRW",
                method=method,
                reference_no=reference_no,
                status="DRAFT",
                version=1,
                unapplied_amount=total_amount,
                allocations=(),
            )
            repo.add(value, actor.user_id)
            stored = repo.get(company, value.id)
            assert stored is not None
            repo.receipt(company, actor.user_id, command, key, digest, stored)
            return stored

    def change(
        self,
        actor: Principal,
        company: UUID,
        kind: str,
        resource: UUID,
        expected_version: int,
        key: str,
        allocations: tuple[Allocation, ...] | None = None,
    ) -> Settlement:
        command = f"{kind}_{'CONFIRM' if allocations is None else 'ALLOCATE'}"
        parts = tuple(
            (str(line.target_id), format(line.allocated_amount, ".4f"), line.expected_version)
            for line in sorted(allocations or (), key=lambda line: line.target_id)
        )
        digest = fingerprint(resource, expected_version, parts)
        with self.factory() as uow:
            require_company(uow, actor, company, permission(kind, command=True))
            require_currency(uow, company)
            uow.lock_command(company, actor.user_id, command, key)
            repo = uow.settlements(kind)
            replay = repo.replay(company, actor.user_id, command, key, digest)
            if replay:
                value = repo.get(company, replay)
                assert value is not None
                return value
            value = repo.get(company, resource, lock=True)
            if value is None:
                raise ResourceNotFound()
            check_version(value.version, expected_version)
            if value.status != "DRAFT":
                raise AccountingError(
                    "STATE_TRANSITION_NOT_ALLOWED", "이미 확정한 배분은 변경할 수 없습니다.", 409
                )
            lines = value.allocations if allocations is None else allocations
            if len({line.target_id for line in lines}) != len(lines):
                raise AccountingError("BUSINESS_RULE_VIOLATION", "배분 대상이 중복되었습니다.")
            if sum((line.allocated_amount for line in lines), Decimal(0)) > value.total_amount:
                raise AccountingError(
                    "SETTLEMENT_ALLOCATION_EXCEEDED", "배분 합계가 수금·지급액을 초과합니다."
                )
            groups: dict[tuple[UUID, UUID], Decimal] = {}
            for line in sorted(lines, key=lambda line: line.target_id):
                positive(line.allocated_amount)
                target = uow.obligations(kind).get(company, line.target_id, date.max, lock=True)
                if target is None:
                    raise ResourceNotFound()
                check_version(target.version, line.expected_version)
                if target.origin_date > value.settlement_date:
                    raise AccountingError(
                        "BUSINESS_RULE_VIOLATION", "발생일 이전에는 배분할 수 없습니다."
                    )
                if line.allocated_amount > target.outstanding_amount:
                    raise AccountingError(
                        "SETTLEMENT_ALLOCATION_EXCEEDED", "배분액이 남은 잔액을 초과합니다."
                    )
                group = (target.account_id, target.counterparty_id)
                groups[group] = groups.get(group, Decimal(0)) + line.allocated_amount
            if allocations is not None:
                repo.replace_allocations(value, lines)
            else:
                self._validate_accounting(uow, company, kind, value, groups)
                repo.confirm(value)
                for line in lines:
                    uow.obligations(kind).refresh(company, line.target_id)
            result = repo.get(company, resource)
            assert result is not None
            repo.receipt(company, actor.user_id, command, key, digest, result)
            uow.governance.audit(
                company,
                actor.user_id,
                command,
                value.journal_entry_id,
                key,
                value.status,
                result.status,
                datetime.now(UTC),
            )
            return result

    @staticmethod
    def _validate_accounting(
        uow: FinanceUnitOfWork,
        company: UUID,
        kind: str,
        value: Settlement,
        allocated: dict[tuple[UUID, UUID], Decimal],
    ) -> None:
        journal = posted_journal(uow, company, value.journal_entry_id)
        actual: dict[tuple[UUID, UUID], Decimal] = {}
        cash = Decimal(0)
        for line in journal.lines:
            account = uow.accounts.get(company_id=company, resource_id=line.account_id)
            assert account is not None
            control = (
                line.credit_amount - line.debit_amount
                if kind == "AR"
                else line.debit_amount - line.credit_amount
            )
            if account.account_name in CONTROL_NAMES[kind]:
                if line.counterparty_id is None or control <= 0:
                    raise AccountingError(
                        "BUSINESS_RULE_VIOLATION", "배분 대상 전표의 거래처와 방향을 확인해 주세요."
                    )
                group = (line.account_id, line.counterparty_id)
                actual[group] = actual.get(group, Decimal(0)) + control
            if account.account_name in {"현금", "보통예금", "당좌예금", "현금및현금성자산"}:
                cash += (
                    line.debit_amount - line.credit_amount
                    if kind == "AR"
                    else line.credit_amount - line.debit_amount
                )
        if actual != allocated or cash != value.total_amount:
            raise AccountingError(
                "SETTLEMENT_JOURNAL_MISMATCH",
                "배분 내역과 확정 전표의 거래처·계정·금액이 일치하지 않습니다.",
                409,
            )
