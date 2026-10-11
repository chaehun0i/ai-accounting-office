"""확정 전표를 근거로 채권채무와 배분 사실을 관리합니다."""

import builtins
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from app.accounting.journals.application.posted_facts import posted_journal
from app.accounting.journals.domain.errors import AccountingError
from app.companies.application.service import require_company
from app.contracts.access_errors import ResourceNotFound
from app.finance.receivables.domain.entities import Obligation
from app.finance.settlements.application.contracts import FinanceUnitOfWork
from app.finance.settlements.domain.entities import Allocation, Settlement
from app.finance.settlements.domain.rules import check_version, positive
from app.identity.users.domain.entities import Principal

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


class FinanceService:
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
            if any(value.journal_entry_id == journal_id for value in repo.list(company)):
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
