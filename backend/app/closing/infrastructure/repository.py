"""회사 범위로 잠그고 읽는 결산 저장소입니다. commit은 작업단위가 소유합니다."""

from dataclasses import fields
from datetime import date, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.accounting.journals.infrastructure.models import JournalModel
from app.accounting.transactions.infrastructure.models import TransactionModel
from app.closing.domain.entities import (
    ClosingAdjustment,
    ClosingApproval,
    ClosingCheckResult,
    ClosingRun,
)
from app.closing.infrastructure.models import (
    ClosingAdjustmentModel,
    ClosingApprovalModel,
    ClosingCheckModel,
    ClosingCommandModel,
    ClosingEventModel,
    ClosingRunModel,
)
from app.contracts.access_errors import ResourceNotFound, StateConflict


def entity[T](row: object, kind: type[T]) -> T:
    return kind(**{field.name: getattr(row, field.name) for field in fields(cast(Any, kind))})


class ClosingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run(self, company: UUID, identifier: UUID, *, lock: bool = False) -> ClosingRun | None:
        query = select(ClosingRunModel).where(
            ClosingRunModel.company_id == company, ClosingRunModel.id == identifier
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        return entity(row, ClosingRun) if row else None

    def runs(self, company: UUID, period: UUID) -> list[ClosingRun]:
        return [
            entity(row, ClosingRun)
            for row in self.session.scalars(
                select(ClosingRunModel)
                .where(
                    ClosingRunModel.company_id == company,
                    ClosingRunModel.accounting_period_id == period,
                )
                .order_by(ClosingRunModel.run_version.desc())
            )
        ]

    def add_run(self, value: ClosingRun) -> None:
        self.session.add(ClosingRunModel(**{f.name: getattr(value, f.name) for f in fields(value)}))
        self.session.flush()

    def update_run(self, value: ClosingRun) -> None:
        row = self.session.scalar(
            select(ClosingRunModel)
            .where(
                ClosingRunModel.company_id == value.company_id,
                ClosingRunModel.id == value.id,
            )
            .with_for_update()
        )
        if row is None:
            raise ResourceNotFound()
        for field in fields(value):
            if field.name != "id":
                setattr(row, field.name, getattr(value, field.name))
        self.session.flush()

    def checks(self, company: UUID, run: UUID) -> tuple[ClosingCheckResult, ...]:
        current = self.session.scalar(
            select(func.max(ClosingCheckModel.check_version)).where(
                ClosingCheckModel.company_id == company,
                ClosingCheckModel.closing_run_id == run,
            )
        )
        if current is None:
            return ()
        return tuple(
            entity(row, ClosingCheckResult)
            for row in self.session.scalars(
                select(ClosingCheckModel)
                .where(
                    ClosingCheckModel.company_id == company,
                    ClosingCheckModel.closing_run_id == run,
                    ClosingCheckModel.check_version == current,
                )
                .order_by(ClosingCheckModel.check_code)
            )
        )

    def replace_checks(
        self, company: UUID, run: UUID, checks: tuple[ClosingCheckResult, ...], now: datetime
    ) -> None:
        current = self.session.scalar(
            select(func.max(ClosingCheckModel.check_version)).where(
                ClosingCheckModel.company_id == company,
                ClosingCheckModel.closing_run_id == run,
            )
        )
        version = (current or 0) + 1
        for value in checks:
            self.session.add(
                ClosingCheckModel(
                    id=uuid4(),
                    company_id=company,
                    closing_run_id=run,
                    check_version=version,
                    check_code=value.check_code,
                    severity=value.severity,
                    result_code=value.result_code,
                    amount_impact=value.amount_impact,
                    source_type=value.source_type,
                    source_id=value.source_id,
                    evidence_ref=value.evidence_ref,
                    created_at=now,
                )
            )
        self.session.flush()

    def adjustments(self, company: UUID, run: UUID) -> list[ClosingAdjustment]:
        return [
            entity(row, ClosingAdjustment)
            for row in self.session.scalars(
                select(ClosingAdjustmentModel)
                .where(
                    ClosingAdjustmentModel.company_id == company,
                    ClosingAdjustmentModel.closing_run_id == run,
                )
                .order_by(ClosingAdjustmentModel.created_at)
            )
        ]

    def adjustment(
        self, company: UUID, identifier: UUID, *, lock: bool = False
    ) -> ClosingAdjustment | None:
        query = select(ClosingAdjustmentModel).where(
            ClosingAdjustmentModel.company_id == company, ClosingAdjustmentModel.id == identifier
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        return entity(row, ClosingAdjustment) if row else None

    def add_adjustment(
        self,
        value: ClosingAdjustment,
        now: datetime,
        source_type: str | None,
        source_id: UUID | None,
    ) -> None:
        self.session.add(
            ClosingAdjustmentModel(
                **{f.name: getattr(value, f.name) for f in fields(value)},
                source_type=source_type,
                source_id=source_id,
                created_at=now,
            )
        )
        self.session.flush()

    def update_adjustment(self, value: ClosingAdjustment, expected_version: int) -> None:
        result = cast(
            CursorResult[Any],
            self.session.execute(
                update(ClosingAdjustmentModel)
                .where(
                    ClosingAdjustmentModel.company_id == value.company_id,
                    ClosingAdjustmentModel.id == value.id,
                    ClosingAdjustmentModel.version == expected_version,
                )
                .values(
                    status=value.status,
                    approval_id=value.approval_id,
                    reversal_journal_id=value.reversal_journal_id,
                    version=value.version,
                )
            ),
        )
        if result.rowcount != 1:
            raise StateConflict()

    def approval(
        self, company: UUID, identifier: UUID, *, lock: bool = False
    ) -> ClosingApproval | None:
        query = select(ClosingApprovalModel).where(
            ClosingApprovalModel.company_id == company, ClosingApprovalModel.id == identifier
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        return entity(row, ClosingApproval) if row else None

    def approvals(self, company: UUID, run: UUID) -> list[ClosingApproval]:
        return [
            entity(row, ClosingApproval)
            for row in self.session.scalars(
                select(ClosingApprovalModel)
                .where(
                    ClosingApprovalModel.company_id == company,
                    ClosingApprovalModel.closing_run_id == run,
                )
                .order_by(ClosingApprovalModel.requested_at.desc())
            )
        ]

    def add_approval(self, value: ClosingApproval) -> None:
        self.session.add(
            ClosingApprovalModel(**{f.name: getattr(value, f.name) for f in fields(value)})
        )
        self.session.flush()

    def update_approval(self, value: ClosingApproval) -> None:
        row = self.session.scalar(
            select(ClosingApprovalModel)
            .where(
                ClosingApprovalModel.company_id == value.company_id,
                ClosingApprovalModel.id == value.id,
            )
            .with_for_update()
        )
        if row is None:
            raise ResourceNotFound()
        row.status = value.status
        row.reviewer_id = value.reviewer_id
        row.decided_at = value.decided_at
        row.reason = value.reason

    def pending(self, company: UUID, start: date, end: date) -> tuple[int, int]:
        journaled = (
            select(JournalModel.id)
            .where(
                JournalModel.company_id == company,
                JournalModel.source_transaction_id == TransactionModel.id,
                JournalModel.status == "POSTED",
            )
            .exists()
        )
        transactions = (
            self.session.scalar(
                select(func.count())
                .select_from(TransactionModel)
                .where(
                    TransactionModel.company_id == company,
                    TransactionModel.accounting_date.between(start, end),
                    TransactionModel.status != "EXCLUDED",
                    ~journaled,
                )
            )
            or 0
        )
        journals = (
            self.session.scalar(
                select(func.count())
                .select_from(JournalModel)
                .where(
                    JournalModel.company_id == company,
                    JournalModel.entry_date.between(start, end),
                    JournalModel.status.in_(("DRAFT", "PROPOSED", "REVIEW_REQUIRED", "APPROVED")),
                )
            )
            or 0
        )
        return transactions, journals

    def replay(
        self, company: UUID, actor: UUID, code: str, key: str, fingerprint: str
    ) -> tuple[UUID, UUID | None, UUID | None] | None:
        row = self.session.scalar(
            select(ClosingCommandModel).where(
                ClosingCommandModel.company_id == company,
                ClosingCommandModel.actor_id == actor,
                ClosingCommandModel.command_code == code,
                ClosingCommandModel.idempotency_key == key,
            )
        )
        if row is None:
            return None
        if row.fingerprint != fingerprint:
            from app.intake.domain.errors import IdempotencyConflict

            raise IdempotencyConflict()
        return row.closing_run_id, row.adjustment_id, row.approval_id

    def record(
        self,
        company: UUID,
        actor: UUID,
        code: str,
        key: str,
        fingerprint: str,
        run: UUID,
        now: datetime,
        adjustment: UUID | None = None,
        approval: UUID | None = None,
        before: str = "",
        after: str = "",
    ) -> None:
        self.session.add(
            ClosingCommandModel(
                id=uuid4(),
                company_id=company,
                actor_id=actor,
                command_code=code,
                idempotency_key=key,
                fingerprint=fingerprint,
                closing_run_id=run,
                adjustment_id=adjustment,
                approval_id=approval,
                occurred_at=now,
            )
        )
        self.session.add(
            ClosingEventModel(
                id=uuid4(),
                company_id=company,
                closing_run_id=run,
                actor_id=actor,
                command_code=code,
                before_digest=before or fingerprint,
                after_digest=after or fingerprint,
                occurred_at=now,
            )
        )
        self.session.flush()
