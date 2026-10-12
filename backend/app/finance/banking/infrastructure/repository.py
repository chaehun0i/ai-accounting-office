"""회사 잠금과 관계형 원천/대사 조회를 담당하며 commit하지 않습니다."""

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.accounting.journals.infrastructure.models import JournalModel
from app.accounting.transactions.infrastructure.models import TransactionModel
from app.contracts.access_errors import VersionConflict
from app.core.digests import digest
from app.finance.banking.domain.entities import (
    FinancialAccount,
    FinancialSource,
    Match,
    ReconciliationItem,
    ReconciliationLine,
    Statement,
)
from app.finance.banking.infrastructure.models import (
    BankAccountModel,
    BankStatementModel,
    BankTransactionModel,
    CardAccountModel,
    CardTransactionModel,
    ReconciliationEventModel,
    ReconciliationItemModel,
    ReconciliationPolicyModel,
)
from app.finance.reconciliation.domain.rules import MatchFact, MatchingPolicy, reconciliation_status
from app.finance.reconciliation.infrastructure.models import (
    ReconciliationMatchLineModel,
    ReconciliationMatchModel,
)
from app.finance.settlements.infrastructure.models import CollectionModel, PaymentModel
from app.intake.domain.errors import IdempotencyConflict
from app.intake.infrastructure.models import ImportModel, ImportReceiptModel
from app.master_data.counterparties.infrastructure.models import CounterpartyModel

ZERO = Decimal("0")


class BankingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock(self, company: UUID) -> None:
        # 같은 회사의 source/target 교차 대사를 같은 순서로 직렬화합니다.
        key = int.from_bytes(
            bytes.fromhex(digest(["bank-reconciliation", str(company)]))[:8], signed=True
        )
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    def accounts(self, company: UUID, kind: str) -> list[FinancialAccount]:
        model = BankAccountModel if kind == "BANK" else CardAccountModel
        return [
            FinancialAccount(
                kind=kind,
                **{k: getattr(r, k) for k in FinancialAccount.__dataclass_fields__ if k != "kind"},
            )
            for r in self.session.scalars(
                select(model).where(model.company_id == company).order_by(model.alias)
            )
        ]

    def account(self, company: UUID, kind: str, identifier: UUID) -> FinancialAccount | None:
        return next((a for a in self.accounts(company, kind) if a.id == identifier), None)

    def add_account(self, value: FinancialAccount) -> None:
        model = BankAccountModel if value.kind == "BANK" else CardAccountModel
        data = asdict(value)
        data.pop("kind")
        self.session.add(model(**data))
        self.session.flush()

    def policy(self, company: UUID) -> MatchingPolicy:
        r = self.session.scalar(
            select(ReconciliationPolicyModel).where(ReconciliationPolicyModel.company_id == company)
        )
        return (
            MatchingPolicy(**{k: getattr(r, k) for k in MatchingPolicy.__dataclass_fields__})
            if r
            else MatchingPolicy()
        )

    def save_policy(self, company: UUID, actor: UUID, value: MatchingPolicy, expected: int) -> None:
        r = self.session.scalar(
            select(ReconciliationPolicyModel)
            .where(ReconciliationPolicyModel.company_id == company)
            .with_for_update()
        )
        if r is None:
            if expected != 0:
                raise VersionConflict()
            self.session.add(
                ReconciliationPolicyModel(company_id=company, updated_by=actor, **asdict(value))
            )
        else:
            if r.version != expected:
                raise VersionConflict()
            for key, val in asdict(value).items():
                setattr(r, key, val)
            r.updated_by = actor
        self.session.flush()

    @staticmethod
    def _statement(r: BankStatementModel) -> Statement:
        return Statement(**{k: getattr(r, k) for k in Statement.__dataclass_fields__})

    def statements(self, company: UUID, account: UUID | None = None) -> list[Statement]:
        q = select(BankStatementModel).where(BankStatementModel.company_id == company)
        if account:
            q = q.where(BankStatementModel.bank_account_id == account)
        return [
            self._statement(r)
            for r in self.session.scalars(
                q.order_by(BankStatementModel.statement_start, BankStatementModel.id)
            )
        ]

    def statement(self, company: UUID, identifier: UUID) -> Statement | None:
        r = self.session.scalar(
            select(BankStatementModel)
            .where(BankStatementModel.company_id == company, BankStatementModel.id == identifier)
            .with_for_update()
        )
        return self._statement(r) if r else None

    def add_statement(self, value: Statement, now: datetime) -> None:
        self.session.add(BankStatementModel(**asdict(value), created_at=now))
        self.session.flush()

    def set_statement(self, value: Statement, status: str) -> None:
        r = self.session.scalar(
            select(BankStatementModel).where(
                BankStatementModel.company_id == value.company_id, BankStatementModel.id == value.id
            )
        )
        assert r is not None
        r.status = status
        r.version += 1
        self.session.flush()

    def _consumed(self, company: UUID, column: str, kind: str, identifier: UUID) -> Decimal:
        line = ReconciliationMatchLineModel
        match = ReconciliationMatchModel
        return (
            self.session.scalar(
                select(func.coalesce(func.sum(line.amount), 0))
                .join(match, match.id == line.reconciliation_match_id)
                .where(
                    line.company_id == company,
                    match.company_id == company,
                    match.status == "CONFIRMED",
                    getattr(line, column + "_type") == kind,
                    getattr(line, column + "_id") == identifier,
                )
            )
            or ZERO
        )

    def _source(
        self, company: UUID, kind: str, r: BankTransactionModel | CardTransactionModel
    ) -> FinancialSource:
        matched = self._consumed(company, "source", kind, r.id)
        data = {
            k: getattr(r, k)
            for k in FinancialSource.__dataclass_fields__
            if k
            not in {
                "kind",
                "balance_after",
                "statement_id",
                "matched_amount",
                "reconciliation_status",
            }
        }
        return FinancialSource(
            **data,
            kind=kind,
            balance_after=getattr(r, "balance_after", None),
            statement_id=getattr(r, "statement_id", None),
            matched_amount=matched,
            reconciliation_status=reconciliation_status(
                r.amount, matched, review=r.source_status in {"AUTHORIZED", "CANCELLED", "REVERSED"}
            ),
        )

    def sources(
        self, company: UUID, kind: str, account: UUID | None = None, statement: UUID | None = None
    ) -> list[FinancialSource]:
        model = BankTransactionModel if kind == "BANK" else CardTransactionModel
        q = select(model).where(model.company_id == company)
        if account:
            q = q.where(model.account_id == account)
        if statement:
            q = q.where(BankTransactionModel.statement_id == statement)
        return [
            self._source(company, kind, cast(BankTransactionModel | CardTransactionModel, r))
            for r in self.session.scalars(q.order_by(model.occurred_at, model.source_id))
        ]

    def source(self, company: UUID, kind: str, identifier: UUID) -> FinancialSource | None:
        model = BankTransactionModel if kind == "BANK" else CardTransactionModel
        r = self.session.scalar(
            select(model)
            .where(model.company_id == company, model.id == identifier)
            .with_for_update()
        )
        return (
            self._source(company, kind, cast(BankTransactionModel | CardTransactionModel, r))
            if r
            else None
        )

    def source_identity(self, company: UUID, value: FinancialSource) -> FinancialSource | None:
        model = BankTransactionModel if value.kind == "BANK" else CardTransactionModel
        r = self.session.scalar(
            select(model).where(
                model.company_id == company,
                model.account_id == value.account_id,
                model.source_system == value.source_system,
                model.source_id == value.source_id,
            )
        )
        return (
            self._source(company, value.kind, cast(BankTransactionModel | CardTransactionModel, r))
            if r
            else None
        )

    def add_source(self, value: FinancialSource, now: datetime) -> None:
        model = BankTransactionModel if value.kind == "BANK" else CardTransactionModel
        data = asdict(value)
        for k in ["kind", "matched_amount", "reconciliation_status"]:
            data.pop(k)
        if value.kind == "CARD":
            data.pop("balance_after")
            data.pop("statement_id")
        self.session.add(model(**data, created_at=now))
        self.session.flush()

    def touch_source(self, company: UUID, kind: str, identifier: UUID) -> None:
        model = BankTransactionModel if kind == "BANK" else CardTransactionModel
        r = self.session.scalar(
            select(model).where(model.company_id == company, model.id == identifier)
        )
        assert r is not None
        cast(BankTransactionModel | CardTransactionModel, r).version += 1
        self.session.flush()

    def _target_version(self, company: UUID, kind: str, identifier: UUID, version: int) -> int:
        line = ReconciliationMatchLineModel
        match = ReconciliationMatchModel
        changes = (
            self.session.scalar(
                select(func.coalesce(func.sum(match.version), 0))
                .join(line, line.reconciliation_match_id == match.id)
                .where(
                    line.company_id == company,
                    match.company_id == company,
                    line.target_type == kind,
                    line.target_id == identifier,
                    match.status != "DRAFT",
                )
            )
            or 0
        )
        return version + int(changes)

    def target(self, company: UUID, kind: str, identifier: UUID) -> MatchFact | None:
        if kind in {"COLLECTION", "PAYMENT"}:
            model = CollectionModel if kind == "COLLECTION" else PaymentModel
            r = self.session.scalar(
                select(model)
                .where(model.company_id == company, model.id == identifier)
                .with_for_update()
            )
            r = cast(CollectionModel | PaymentModel | None, r)
            if r is None or r.status not in {"CONFIRMED", "UNAPPLIED"}:
                return None
            occurred = r.received_date if isinstance(r, CollectionModel) else r.payment_date
            return MatchFact(
                r.id,
                kind,
                occurred,
                "IN" if kind == "COLLECTION" else "OUT",
                r.total_amount,
                self._consumed(company, "target", kind, r.id),
                self._target_version(company, kind, r.id, r.version),
                r.reference_no,
            )
        if kind != "TRANSACTION":
            return None
        transaction = self.session.scalar(
            select(TransactionModel)
            .where(TransactionModel.company_id == company, TransactionModel.id == identifier)
            .with_for_update()
        )
        r = transaction
        if r is None or r.direction not in {"INFLOW", "OUTFLOW"} or r.status == "CANCELLED":
            return None
        # 같은 경제사건을 수금/지급과 거래 양쪽으로 중복 소비하지 않습니다.
        settlement_models: tuple[type[CollectionModel] | type[PaymentModel], ...] = (
            CollectionModel,
            PaymentModel,
        )
        for settlement_model in settlement_models:
            linked = self.session.scalar(
                select(settlement_model.id)
                .join(JournalModel, JournalModel.id == settlement_model.journal_entry_id)
                .where(
                    settlement_model.company_id == company,
                    JournalModel.company_id == company,
                    JournalModel.source_transaction_id == r.id,
                )
            )
            if linked:
                return None
        party = (
            self.session.scalar(
                select(CounterpartyModel.display_name).where(
                    CounterpartyModel.company_id == company,
                    CounterpartyModel.id == r.counterparty_id,
                )
            )
            if r.counterparty_id
            else ""
        )
        return MatchFact(
            r.id,
            kind,
            r.transaction_date,
            "IN" if r.direction == "INFLOW" else "OUT",
            r.amount,
            self._consumed(company, "target", kind, r.id),
            self._target_version(company, kind, r.id, r.version),
            r.source_id,
            party or "",
        )

    def targets(self, company: UUID, from_date: date, to_date: date) -> list[MatchFact]:
        result: list[MatchFact] = []
        queries = [
            (
                "COLLECTION",
                select(CollectionModel.id).where(
                    CollectionModel.company_id == company,
                    CollectionModel.received_date >= from_date,
                    CollectionModel.received_date <= to_date,
                ),
            ),
            (
                "PAYMENT",
                select(PaymentModel.id).where(
                    PaymentModel.company_id == company,
                    PaymentModel.payment_date >= from_date,
                    PaymentModel.payment_date <= to_date,
                ),
            ),
            (
                "TRANSACTION",
                select(TransactionModel.id).where(
                    TransactionModel.company_id == company,
                    TransactionModel.transaction_date >= from_date,
                    TransactionModel.transaction_date <= to_date,
                ),
            ),
        ]
        for kind, query in queries:
            for identifier in self.session.scalars(query):
                fact = self.target(company, kind, identifier)
                if fact and fact.remaining > ZERO:
                    result.append(fact)
        return result

    def match(self, company: UUID, identifier: UUID) -> Match | None:
        r = self.session.scalar(
            select(ReconciliationMatchModel)
            .where(
                ReconciliationMatchModel.company_id == company,
                ReconciliationMatchModel.id == identifier,
            )
            .with_for_update()
        )
        if r is None:
            return None
        lines = tuple(
            ReconciliationLine(
                **{k: getattr(line, k) for k in ReconciliationLine.__dataclass_fields__}
            )
            for line in self.session.scalars(
                select(ReconciliationMatchLineModel)
                .where(
                    ReconciliationMatchLineModel.company_id == company,
                    ReconciliationMatchLineModel.reconciliation_match_id == identifier,
                )
                .order_by(
                    ReconciliationMatchLineModel.source_id, ReconciliationMatchLineModel.target_id
                )
            )
        )
        return Match(
            id=r.id,
            company_id=company,
            match_type=r.match_type,
            status=r.status,
            matched_amount=r.matched_amount,
            version=r.version,
            created_by=r.created_by,
            lines=lines,
            unmatch_reason=r.unmatch_reason,
        )

    def matches(self, company: UUID) -> list[Match]:
        ids = self.session.scalars(
            select(ReconciliationMatchModel.id)
            .where(ReconciliationMatchModel.company_id == company)
            .order_by(ReconciliationMatchModel.created_at)
        ).all()
        return [v for identifier in ids if (v := self.match(company, identifier)) is not None]

    def add_match(self, value: Match, now: datetime) -> None:
        data = asdict(value)
        data.pop("lines")
        self.session.add(ReconciliationMatchModel(**data, created_at=now))
        self.session.flush()
        for line in value.lines:
            data = asdict(line)
            data["bank_transaction_id" if line.source_type == "BANK" else "card_transaction_id"] = (
                line.source_id
            )
            data[
                {
                    "COLLECTION": "collection_id",
                    "PAYMENT": "payment_id",
                    "TRANSACTION": "transaction_id",
                }[line.target_type]
            ] = line.target_id
            self.session.add(
                ReconciliationMatchLineModel(
                    company_id=value.company_id, reconciliation_match_id=value.id, **data
                )
            )
        self.session.flush()

    def set_match(
        self, value: Match, status: str, actor: UUID, now: datetime, reason: str | None = None
    ) -> None:
        r = self.session.scalar(
            select(ReconciliationMatchModel).where(
                ReconciliationMatchModel.company_id == value.company_id,
                ReconciliationMatchModel.id == value.id,
            )
        )
        assert r is not None
        r.status = status
        r.version += 1
        if status == "CONFIRMED":
            r.confirmed_by = actor
            r.confirmed_at = now
        else:
            r.unmatched_by = actor
            r.unmatched_at = now
            r.unmatch_reason = reason
        self.session.flush()

    def items(self, company: UUID, statement: UUID) -> list[ReconciliationItem]:
        return [
            ReconciliationItem(
                **{k: getattr(r, k) for k in ReconciliationItem.__dataclass_fields__}
            )
            for r in self.session.scalars(
                select(ReconciliationItemModel)
                .where(
                    ReconciliationItemModel.company_id == company,
                    ReconciliationItemModel.statement_id == statement,
                )
                .order_by(ReconciliationItemModel.created_at)
            )
        ]

    def add_item(self, value: ReconciliationItem, actor: UUID, now: datetime) -> None:
        self.session.add(ReconciliationItemModel(**asdict(value), created_by=actor, created_at=now))
        self.session.flush()

    def replay(
        self, company: UUID, actor: UUID, command: str, key: str, fingerprint: str
    ) -> UUID | None:
        r = self.session.scalar(
            select(ReconciliationEventModel).where(
                ReconciliationEventModel.company_id == company,
                ReconciliationEventModel.actor_id == actor,
                ReconciliationEventModel.command_code == command,
                ReconciliationEventModel.idempotency_key == key,
            )
        )
        if r is None:
            return None
        if r.fingerprint != fingerprint:
            raise IdempotencyConflict()
        return r.statement_id or r.reconciliation_id or r.card_account_id

    def event(
        self,
        company: UUID,
        actor: UUID,
        command: str,
        key: str,
        fingerprint: str,
        kind: str,
        result: UUID,
        version: int,
        now: datetime,
    ) -> None:
        column = {
            "STATEMENT": "statement_id",
            "MATCH": "reconciliation_id",
            "CARD": "card_account_id",
        }[kind]
        self.session.add(
            ReconciliationEventModel(
                company_id=company,
                actor_id=actor,
                command_code=command,
                idempotency_key=key,
                fingerprint=fingerprint,
                result_version=version,
                created_at=now,
                **{column: result},
            )
        )
        self.session.flush()

    def complete_import(self, company: UUID, identifier: UUID, now: datetime) -> None:
        r = self.session.scalar(
            select(ImportModel)
            .where(ImportModel.company_id == company, ImportModel.id == identifier)
            .with_for_update()
        )
        receipt = self.session.scalar(
            select(ImportReceiptModel).where(
                ImportReceiptModel.company_id == company, ImportReceiptModel.import_id == identifier
            )
        )
        assert r is not None and receipt is not None
        if r.status == "CONFIRMED":
            r.status = "COMPLETED"
            r.version += 1
            r.completed_at = now
            r.updated_at = now
            receipt.status = "COMPLETED"
            receipt.promoted_at = now
        self.session.flush()
