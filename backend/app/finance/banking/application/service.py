"""확정 파일의 금융 원천 승격은 장부 변경 권한을 갖지 않습니다."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.accounting.application.service import AccountingMasterService
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.core.digests import digest
from app.core.values import require_money
from app.finance.banking.application.contracts import BankingUnitOfWork
from app.finance.banking.domain.entities import FinancialAccount, FinancialSource, Statement
from app.finance.banking.domain.normalization import financial_text, normalize_row
from app.finance.reconciliation.domain.rules import (
    MatchFact,
    MatchingPolicy,
    StatementNotBalanced,
    closing_balance,
    safe_reference,
)
from app.identity.users.domain.entities import Principal
from app.intake.application.service import IntakeService
from app.intake.domain.canonical_fields import SourceType, TargetContext
from app.intake.domain.errors import PreviewStale, SourceConflict


class BankingService:
    def __init__(self, factory: Callable[[], BankingUnitOfWork], intake: IntakeService) -> None:
        self.factory = factory
        self.intake = intake

    def accounts(self, actor: Principal, company: UUID, kind: str) -> list[FinancialAccount]:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            return uow.banking.accounts(company, kind)

    def create_account(
        self,
        actor: Principal,
        company: UUID,
        kind: str,
        institution: str,
        alias: str,
        control: UUID,
        usage_type: str = "CORPORATE",
    ) -> FinancialAccount:
        safe_reference(institution, maximum=30)
        alias = financial_text(alias, 80)
        if not alias:
            raise InvalidInput()
        if usage_type not in {"CORPORATE", "MERCHANT"} or (
            kind == "BANK" and usage_type != "CORPORATE"
        ):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.manage")
            uow.banking.lock(company)
            AccountingMasterService.map_control_in(
                uow,
                actor,
                company,
                control,
                "BANK_CASH"
                if kind == "BANK"
                else "CARD_CLEARING"
                if usage_type == "MERCHANT"
                else "CARD_PAYABLE",
            )
            if any(a.alias == alias for a in uow.banking.accounts(company, kind)):
                raise StateConflict()
            # 하나의 GL 통제계정을 여러 계좌로 나누면 계좌별 비교가 모호해집니다.
            if any(a.control_account_id == control for a in uow.banking.accounts(company, kind)):
                raise StateConflict()
            result = FinancialAccount(
                id=uuid4(),
                company_id=company,
                kind=kind,
                institution_code=institution,
                alias=alias,
                control_account_id=control,
                usage_type=usage_type,
            )
            uow.banking.add_account(result)
            return result

    def policy(self, actor: Principal, company: UUID) -> MatchingPolicy:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            return uow.banking.policy(company)

    def update_policy(
        self, actor: Principal, company: UUID, value: MatchingPolicy, expected: int
    ) -> MatchingPolicy:
        value.validate()
        with self.factory() as uow:
            require_company(uow, actor, company, "control_account.manage")
            uow.banking.lock(company)
            current = uow.banking.policy(company)
            version = 1 if expected == 0 else current.version + 1
            saved = replace(value, version=version)
            uow.banking.save_policy(company, actor.user_id, saved, expected)
            return saved

    def statements(
        self, actor: Principal, company: UUID, account: UUID | None = None
    ) -> list[Statement]:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            return uow.banking.statements(company, account)

    def statement(self, actor: Principal, company: UUID, identifier: UUID) -> Statement:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            result = uow.banking.statement(company, identifier)
            if result is None:
                raise ResourceNotFound()
            return result

    def sources(
        self,
        actor: Principal,
        company: UUID,
        kind: str,
        account: UUID | None = None,
        statement: UUID | None = None,
    ) -> list[FinancialSource]:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            if account and uow.banking.account(company, kind, account) is None:
                raise ResourceNotFound()
            if statement and uow.banking.statement(company, statement) is None:
                raise ResourceNotFound()
            return uow.banking.sources(company, kind, account, statement)

    def import_source(
        self,
        actor: Principal,
        company: UUID,
        kind: str,
        account_id: UUID,
        import_id: UUID,
        receipt_id: UUID,
        source_digest: str,
        confirmed_version: int,
        key: str,
        start: date | None = None,
        end: date | None = None,
        opening: Decimal | None = None,
        closing: Decimal | None = None,
    ) -> Statement | list[FinancialSource]:
        safe_reference(key)
        command = "BANK_IMPORT" if kind == "BANK" else "CARD_IMPORT"
        fingerprint = digest(
            [
                command,
                str(account_id),
                str(import_id),
                str(receipt_id),
                source_digest,
                confirmed_version,
                str(start),
                str(end),
                str(opening),
                str(closing),
            ]
        )
        # 파일 I/O는 잠금 밖에서 수행하고 최종 transaction 안에서 영수증을 다시 결합합니다.
        data = self.intake.confirmed_rows(
            actor,
            company,
            import_id,
            receipt_id=receipt_id,
            source_digest=source_digest,
            confirmed_version=confirmed_version,
        )
        expected_source = (
            SourceType.BANK_TRANSACTION if kind == "BANK" else SourceType.CARD_TRANSACTION
        )
        expected_target = TargetContext.BANK_SOURCE if kind == "BANK" else TargetContext.CARD_SOURCE
        if (
            data.source.source_type != expected_source
            or data.source.target_context != expected_target
        ):
            raise StateConflict()
        statement_id = uuid4() if kind == "BANK" else None
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.manage")
            account = uow.banking.account(company, kind, account_id)
            if account is None:
                raise ResourceNotFound()
            usage_type = account.usage_type
        sources = [
            normalize_row(
                data.source, data.receipt, row, account_id, kind, statement_id, usage_type
            )
            for row in data.rows
        ]
        if kind == "BANK":
            if start is None or end is None or opening is None or closing is None or start > end:
                raise InvalidInput()
            require_money(opening)
            require_money(closing)
            if any(not start <= s.occurred_at.date() <= end for s in sources):
                raise InvalidInput()
            facts = [
                MatchFact(
                    s.id, s.kind, s.occurred_at.date(), s.direction, s.amount, Decimal(0), s.version
                )
                for s in sources
            ]
            if closing_balance(opening, facts) != closing:
                raise StatementNotBalanced()
            # 잔액 열이 제공된 경우 행 순서를 임의 정렬하지 않고 원본 순서로 검증합니다.
            running = opening
            for s in sources:
                running += s.amount if s.direction == "IN" else -s.amount
                if s.balance_after is not None and s.balance_after != running:
                    raise StatementNotBalanced()
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.manage")
            require_company(uow, actor, company, "import.confirm")
            uow.banking.lock(company)
            uow.lock_command(company, actor.user_id, command, key)
            account = uow.banking.account(company, kind, account_id)
            if account is None:
                raise ResourceNotFound()
            if account.status != "ACTIVE":
                raise StateConflict()
            current = uow.imports.get(company_id=company, resource_id=import_id)
            receipt = uow.imports.receipt(company_id=company, import_id=import_id)
            if current is None or receipt is None:
                raise ResourceNotFound()
            if (
                current.version != data.source.version
                or current.file_sha256 != data.source.file_sha256
                or receipt.source_digest != source_digest
                or receipt.confirmed_version != confirmed_version
            ):
                raise PreviewStale()
            replay = uow.banking.replay(company, actor.user_id, command, key, fingerprint)
            if replay:
                if kind == "BANK":
                    result = uow.banking.statement(company, replay)
                    assert result is not None
                    return result
                return uow.banking.sources(company, kind, account_id)
            # 같은 접수 행을 다른 카드/계좌의 새 경제사건으로 복제하지 않습니다.
            if any(
                old.source_import_id == import_id and old.account_id != account_id
                for old in uow.banking.sources(company, kind)
            ):
                raise SourceConflict()
            if kind == "BANK":
                assert (
                    start is not None
                    and end is not None
                    and opening is not None
                    and closing is not None
                    and statement_id is not None
                )
                for old in uow.banking.statements(company, account_id):
                    if old.statement_start <= end and start <= old.statement_end:
                        if (
                            old.statement_start == start
                            and old.statement_end == end
                            and old.source_digest == source_digest
                            and old.opening_balance == opening
                            and old.closing_balance == closing
                        ):
                            uow.banking.event(
                                company,
                                actor.user_id,
                                command,
                                key,
                                fingerprint,
                                "STATEMENT",
                                old.id,
                                old.version,
                                uow.now(),
                            )
                            uow.banking.complete_import(company, import_id, uow.now())
                            return old
                        raise SourceConflict()
                statement = Statement(
                    id=statement_id,
                    company_id=company,
                    bank_account_id=account_id,
                    statement_start=start,
                    statement_end=end,
                    opening_balance=opening.quantize(Decimal("0.0001")),
                    closing_balance=closing.quantize(Decimal("0.0001")),
                    source_import_id=import_id,
                    source_receipt_id=receipt_id,
                    source_digest=source_digest,
                )
                uow.banking.add_statement(statement, uow.now())
            for source in sorted(sources, key=lambda s: s.source_id):
                old_source = uow.banking.source_identity(company, source)
                if old_source:
                    if old_source.source_fingerprint != source.source_fingerprint:
                        raise SourceConflict()
                    if kind == "BANK":
                        raise SourceConflict()
                else:
                    uow.banking.add_source(source, uow.now())
            uow.banking.complete_import(company, import_id, uow.now())
            uow.banking.event(
                company,
                actor.user_id,
                command,
                key,
                fingerprint,
                "STATEMENT" if kind == "BANK" else "CARD",
                statement_id or account_id,
                1,
                uow.now(),
            )
            if kind == "BANK":
                return statement
            return uow.banking.sources(company, kind, account_id)
