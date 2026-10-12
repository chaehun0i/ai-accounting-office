"""대사는 증빙과 업무 사실을 연결할 뿐 전표를 생성하거나 수정하지 않습니다."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from app.companies.application.service import require_company
from app.contracts.access_errors import (
    InvalidInput,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.core.digests import digest
from app.finance.banking.application.contracts import BankingUnitOfWork
from app.finance.banking.domain.entities import (
    CardSummary,
    FinancialSource,
    Match,
    ReconciliationItem,
    ReconciliationLine,
    StatementSummary,
)
from app.finance.banking.domain.normalization import financial_text
from app.finance.reconciliation.domain.rules import (
    AmountExceeded,
    Candidate,
    MatchFact,
    SourceStale,
    UnmatchReasonRequired,
    money,
    safe_reference,
    score_candidate,
)
from app.identity.users.domain.entities import Principal

ZERO = Decimal("0")


def source_fact(value: FinancialSource) -> MatchFact:
    return MatchFact(
        value.id,
        value.kind,
        value.occurred_at.date(),
        value.direction,
        value.amount,
        value.matched_amount,
        value.version,
        value.reference,
        value.counterparty_text,
        value.source_status,
    )


class BankReconciliationService:
    def __init__(self, factory: Callable[[], BankingUnitOfWork]) -> None:
        self.factory = factory

    def candidates(
        self, actor: Principal, company: UUID, kind: str, source_id: UUID
    ) -> list[Candidate]:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            source = uow.banking.source(company, kind, source_id)
            if source is None:
                raise ResourceNotFound()
            policy = uow.banking.policy(company)
            targets = uow.banking.targets(
                company,
                source.occurred_at.date() - timedelta(days=policy.allowed_days),
                source.occurred_at.date() + timedelta(days=policy.allowed_days),
            )
            result = [
                c
                for t in targets
                if (c := score_candidate(source_fact(source), t, policy)) is not None
            ]
            return sorted(result, key=lambda c: (-c.score, c.target_type, str(c.target_id)))

    def statement_candidates(
        self, actor: Principal, company: UUID, identifier: UUID
    ) -> list[Candidate]:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            statement = uow.banking.statement(company, identifier)
            if statement is None:
                raise ResourceNotFound()
            policy = uow.banking.policy(company)
            sources = uow.banking.sources(company, "BANK", statement=identifier)
            targets = uow.banking.targets(
                company,
                statement.statement_start - timedelta(days=policy.allowed_days),
                statement.statement_end + timedelta(days=policy.allowed_days),
            )
            result = [
                c
                for s in sources
                for t in targets
                if (c := score_candidate(source_fact(s), t, policy)) is not None
            ]
            return sorted(
                result, key=lambda c: (str(c.source_id), -c.score, c.target_type, str(c.target_id))
            )

    def matches(self, actor: Principal, company: UUID) -> list[Match]:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            return uow.banking.matches(company)

    def get(self, actor: Principal, company: UUID, identifier: UUID) -> Match:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            result = uow.banking.match(company, identifier)
            if result is None:
                raise ResourceNotFound()
            return result

    @staticmethod
    def _validate(
        uow: BankingUnitOfWork,
        company: UUID,
        lines: tuple[ReconciliationLine, ...],
        *,
        versions: bool,
    ) -> None:
        sources: dict[tuple[str, UUID], Decimal] = defaultdict(lambda: ZERO)
        targets: dict[tuple[str, UUID], Decimal] = defaultdict(lambda: ZERO)
        seen = set()
        for line in lines:
            money(line.amount)
            identity = (line.source_type, line.source_id, line.target_type, line.target_id)
            if identity in seen:
                raise InvalidInput()
            seen.add(identity)
            if line.source_type not in {"BANK", "CARD"} or line.target_type not in {
                "TRANSACTION",
                "COLLECTION",
                "PAYMENT",
            }:
                raise InvalidInput()
            source = uow.banking.source(company, line.source_type, line.source_id)
            target = uow.banking.target(company, line.target_type, line.target_id)
            if source is None or target is None:
                raise ResourceNotFound()
            if versions and (
                source.version != line.source_version or target.version != line.target_version
            ):
                raise SourceStale()
            if (
                source.source_status in {"AUTHORIZED", "CANCELLED", "REVERSED"}
                or source.direction != target.direction
            ):
                raise StateConflict()
            if source.statement_id:
                statement = uow.banking.statement(company, source.statement_id)
                if statement is None:
                    raise ResourceNotFound()
                if statement.status == "CLOSED":
                    raise StateConflict()
            sources[(line.source_type, line.source_id)] += line.amount
            targets[(line.target_type, line.target_id)] += line.amount
        for (kind, identifier), amount in sources.items():
            source = uow.banking.source(company, kind, identifier)
            assert source is not None
            if amount > source.amount - source.matched_amount:
                raise AmountExceeded()
        for (kind, identifier), amount in targets.items():
            target = uow.banking.target(company, kind, identifier)
            assert target is not None
            if amount > target.remaining:
                raise AmountExceeded()

    def create(
        self, actor: Principal, company: UUID, lines: tuple[ReconciliationLine, ...], key: str
    ) -> Match:
        if not 1 <= len(lines) <= 500:
            raise InvalidInput()
        lines = tuple(
            replace(line, amount=money(line.amount).quantize(Decimal("0.0001"))) for line in lines
        )
        safe_reference(key)
        fingerprint = digest(
            [
                "MATCH_CREATE",
                [
                    [(str(getattr(line, k))) for k in ReconciliationLine.__dataclass_fields__]
                    for line in lines
                ],
            ]
        )
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.manage")
            uow.banking.lock(company)
            replay = uow.banking.replay(company, actor.user_id, "MATCH_CREATE", key, fingerprint)
            if replay:
                value = uow.banking.match(company, replay)
                assert value is not None
                return value
            self._validate(uow, company, lines, versions=True)
            counts = (
                len({(line.source_type, line.source_id) for line in lines}),
                len({(line.target_type, line.target_id) for line in lines}),
            )
            relation = (
                "ONE_TO_ONE"
                if counts == (1, 1)
                else "ONE_TO_MANY"
                if counts[0] == 1
                else "MANY_TO_ONE"
                if counts[1] == 1
                else "MANY_TO_MANY"
            )
            value = Match(
                id=uuid4(),
                company_id=company,
                match_type=relation,
                status="DRAFT",
                matched_amount=sum((line.amount for line in lines), ZERO),
                version=1,
                created_by=actor.user_id,
                lines=lines,
            )
            uow.banking.add_match(value, uow.now())
            uow.banking.event(
                company,
                actor.user_id,
                "MATCH_CREATE",
                key,
                fingerprint,
                "MATCH",
                value.id,
                value.version,
                uow.now(),
            )
            return value

    def command(
        self,
        actor: Principal,
        company: UUID,
        identifier: UUID,
        expected: int,
        key: str,
        *,
        unmatch: bool = False,
        reason: str = "",
    ) -> Match:
        safe_reference(key)
        if unmatch and not reason.strip():
            raise UnmatchReasonRequired()
        reason = financial_text(reason, 500)
        command = "UNMATCH" if unmatch else "MATCH_CONFIRM"
        fingerprint = digest([command, str(identifier), expected, reason])
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.manage")
            uow.banking.lock(company)
            replay = uow.banking.replay(company, actor.user_id, command, key, fingerprint)
            value = uow.banking.match(company, identifier)
            if value is None:
                raise ResourceNotFound()
            if replay:
                return value
            if value.version != expected:
                raise SourceStale()
            if value.status != ("CONFIRMED" if unmatch else "DRAFT"):
                raise StateConflict()
            if not unmatch:
                self._validate(uow, company, value.lines, versions=True)
            else:
                for line in value.lines:
                    source = uow.banking.source(company, line.source_type, line.source_id)
                    if source and source.statement_id:
                        statement = uow.banking.statement(company, source.statement_id)
                        if statement and statement.status == "CLOSED":
                            raise StateConflict()
            uow.banking.set_match(
                value,
                "UNMATCHED" if unmatch else "CONFIRMED",
                actor.user_id,
                uow.now(),
                reason if unmatch else None,
            )
            for kind, source_id in sorted(
                {(line.source_type, line.source_id) for line in value.lines},
                key=lambda x: (x[0], str(x[1])),
            ):
                uow.banking.touch_source(company, kind, source_id)
            for statement_id in {
                s.statement_id
                for line in value.lines
                if (s := uow.banking.source(company, line.source_type, line.source_id)) is not None
                and s.statement_id
            }:
                statement = uow.banking.statement(company, statement_id)
                assert statement is not None
                uow.banking.set_statement(statement, "RECONCILING")
            result = uow.banking.match(company, identifier)
            assert result is not None
            uow.banking.event(
                company,
                actor.user_id,
                command,
                key,
                fingerprint,
                "MATCH",
                result.id,
                result.version,
                uow.now(),
            )
            return result

    @staticmethod
    def _summary(uow: BankingUnitOfWork, company: UUID, identifier: UUID) -> StatementSummary:
        statement = uow.banking.statement(company, identifier)
        if statement is None:
            raise ResourceNotFound()
        account = uow.banking.account(company, "BANK", statement.bank_account_id)
        assert account is not None
        source = uow.banking.sources(company, "BANK", statement=identifier)
        facts = uow.ledger.facts(company, statement.statement_end, account.control_account_id)
        gl = sum((f.debit_amount - f.credit_amount for f in facts), ZERO)
        reconciled = statement.opening_balance + sum(
            (s.matched_amount if s.direction == "IN" else -s.matched_amount for s in source), ZERO
        )
        unmatched = sum(s.reconciliation_status == "UNMATCHED" for s in source)
        partial = sum(s.reconciliation_status == "PARTIAL" for s in source)
        review = sum(s.reconciliation_status == "REVIEW" for s in source)
        items = sum(i.status == "OPEN" for i in uow.banking.items(company, identifier))
        difference = statement.closing_balance - gl
        return StatementSummary(
            statement_id=identifier,
            as_of=statement.statement_end,
            account_id=account.control_account_id,
            statement_balance=statement.closing_balance,
            reconciled_source_balance=reconciled,
            gl_balance=gl,
            difference_amount=difference,
            source_total=sum((s.amount for s in source), ZERO),
            matched=sum((s.matched_amount for s in source), ZERO),
            review=review,
            unmatched=unmatched,
            partial=partial,
            unmatched_count=unmatched,
            partial_count=partial,
            review_count=review,
            reconciliation_item_count=items,
            blocker=bool(difference or unmatched or partial or review or items),
        )

    def summary(self, actor: Principal, company: UUID, identifier: UUID) -> StatementSummary:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            require_company(uow, actor, company, "ledger.read")
            uow.banking.lock(company)
            return self._summary(uow, company, identifier)

    def period_summary(
        self, actor: Principal, company: UUID, period_id: UUID
    ) -> list[StatementSummary]:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            require_company(uow, actor, company, "ledger.read")
            period = uow.periods.get(company_id=company, resource_id=period_id)
            if period is None:
                raise ResourceNotFound()
            return [
                self._summary(uow, company, s.id)
                for s in uow.banking.statements(company)
                if period.start_date <= s.statement_end <= period.end_date
            ]

    def items(self, actor: Principal, company: UUID, identifier: UUID) -> list[ReconciliationItem]:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            if uow.banking.statement(company, identifier) is None:
                raise ResourceNotFound()
            return uow.banking.items(company, identifier)

    def item(
        self,
        actor: Principal,
        company: UUID,
        identifier: UUID,
        reason: str,
        amount: Decimal,
        description: str,
        key: str,
    ) -> ReconciliationItem:
        if reason not in {
            "TIMING_ITEM",
            "MISSING_TRANSACTION",
            "DUPLICATE_SOURCE",
            "WRONG_ACCOUNT",
            "MANUAL_ADJUSTMENT_CANDIDATE",
            "UNKNOWN",
        }:
            raise InvalidInput()
        from app.core.values import require_money

        require_money(amount)
        description = financial_text(description, 500)
        safe_reference(key)
        signature = digest([str(identifier), reason, str(amount), description])
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.manage")
            uow.banking.lock(company)
            statement = uow.banking.statement(company, identifier)
            if statement is None:
                raise ResourceNotFound()
            if statement.status == "CLOSED":
                raise StateConflict()
            replay = uow.banking.replay(company, actor.user_id, "ITEM_CREATE", key, signature)
            if replay:
                candidates = uow.banking.items(company, identifier)
                return next(
                    i
                    for i in candidates
                    if i.reason_code == reason
                    and i.amount == amount
                    and i.description == description
                )
            value = ReconciliationItem(
                id=uuid4(),
                company_id=company,
                statement_id=identifier,
                reason_code=reason,
                amount=amount,
                status="OPEN",
                description=description,
            )
            uow.banking.add_item(value, actor.user_id, uow.now())
            uow.banking.event(
                company,
                actor.user_id,
                "ITEM_CREATE",
                key,
                signature,
                "STATEMENT",
                identifier,
                statement.version,
                uow.now(),
            )
            return value

    def close(
        self, actor: Principal, company: UUID, identifier: UUID, expected: int, key: str
    ) -> StatementSummary:
        safe_reference(key)
        signature = digest(["STATEMENT_CLOSE", str(identifier), expected])
        with self.factory() as uow:
            require_company(uow, actor, company, "bank_statement.close")
            require_company(uow, actor, company, "ledger.read")
            uow.banking.lock(company)
            replay = uow.banking.replay(company, actor.user_id, "STATEMENT_CLOSE", key, signature)
            statement = uow.banking.statement(company, identifier)
            if statement is None:
                raise ResourceNotFound()
            summary = self._summary(uow, company, identifier)
            if replay:
                return summary
            if statement.version != expected:
                raise VersionConflict()
            if statement.status == "CLOSED" or summary.blocker:
                raise StateConflict()
            uow.banking.set_statement(statement, "CLOSED")
            uow.banking.event(
                company,
                actor.user_id,
                "STATEMENT_CLOSE",
                key,
                signature,
                "STATEMENT",
                identifier,
                statement.version + 1,
                uow.now(),
            )
            return summary

    def card_summary(
        self, actor: Principal, company: UUID, identifier: UUID, as_of: date
    ) -> CardSummary:
        with self.factory() as uow:
            require_company(uow, actor, company, "reconciliation.read")
            require_company(uow, actor, company, "ledger.read")
            uow.banking.lock(company)
            account = uow.banking.account(company, "CARD", identifier)
            if account is None:
                raise ResourceNotFound()
            rows = [
                source
                for source in uow.banking.sources(company, "CARD", identifier)
                if source.occurred_at.date() <= as_of
            ]
            # 승인만 받은 건과 취소된 승인은 부채 원금으로 인식하지 않습니다.
            effective = [
                source for source in rows if source.source_status in {"CAPTURED", "REFUNDED"}
            ]
            total = sum(
                (
                    source.amount if source.direction == "OUT" else -source.amount
                    for source in effective
                ),
                ZERO,
            )
            reconciled = sum(
                (
                    source.matched_amount if source.direction == "OUT" else -source.matched_amount
                    for source in effective
                ),
                ZERO,
            )
            facts = uow.ledger.facts(company, as_of, account.control_account_id)
            gl = sum((fact.credit_amount - fact.debit_amount for fact in facts), ZERO)
            unmatched = sum(source.reconciliation_status == "UNMATCHED" for source in rows)
            partial = sum(source.reconciliation_status == "PARTIAL" for source in rows)
            review = sum(source.reconciliation_status == "REVIEW" for source in rows)
            return CardSummary(
                card_account_id=identifier,
                account_id=account.control_account_id,
                as_of=as_of,
                source_balance=total,
                reconciled_source_balance=reconciled,
                gl_balance=gl,
                difference_amount=total - gl,
                unmatched_count=unmatched,
                partial_count=partial,
                review_count=review,
                blocker=bool(total - gl or unmatched or partial or review),
            )
