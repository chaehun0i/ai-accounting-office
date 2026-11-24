"""Append-only human review of immutable five-statement revisions."""

import re
from uuid import UUID, uuid4

from sqlalchemy import select

from app.closing.domain.errors import ClosingRunStale
from app.companies.application.service import require_company
from app.contracts.access_errors import (
    InvalidInput,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.contracts.errors import ApplicationError
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.equity.service import EquityService, _row
from app.reporting.financial_statements.domain.rules import ReportSourceStale
from app.reporting.statement_sets.models import StatementSetRevisionModel
from app.reporting.statement_sets.review_models import StatementSetReviewModel


class StatementSetApprovalRequired(ApplicationError):
    code = "STATEMENT_SET_APPROVAL_REQUIRED"
    status_code = 409
    message = "현재 재무제표 세트의 독립 검토 승인을 먼저 완료해 주세요."


def latest_review(
    uow: CashFlowUnitOfWork, company: UUID, statement: UUID
) -> StatementSetReviewModel | None:
    return uow.session.scalar(
        select(StatementSetReviewModel)
        .where(
            StatementSetReviewModel.company_id == company,
            StatementSetReviewModel.statement_id == statement,
        )
        .order_by(StatementSetReviewModel.version.desc())
        .limit(1)
    )


def require_set_approval(
    uow: CashFlowUnitOfWork, statement: StatementSetRevisionModel
) -> StatementSetReviewModel:
    review = latest_review(uow, statement.company_id, statement.id)
    if (
        review is None
        or review.status != "APPROVED"
        or review.source_digest != statement.snapshot_digest
    ):
        raise StatementSetApprovalRequired()
    return review


class StatementSetReviewService:
    def __init__(self, equity: EquityService) -> None:
        self.equity = equity

    def _statement(
        self, uow: CashFlowUnitOfWork, company: UUID, identifier: UUID
    ) -> StatementSetRevisionModel:
        statement = uow.session.scalar(
            select(StatementSetRevisionModel).where(
                StatementSetRevisionModel.company_id == company,
                StatementSetRevisionModel.id == identifier,
            )
        )
        if statement is None:
            raise ResourceNotFound()
        return statement

    def _current(self, uow: CashFlowUnitOfWork, statement: StatementSetRevisionModel) -> bool:
        try:
            from app.reporting.statement_sets.service import StatementSetService

            state = StatementSetService(self.equity.factory).collect(
                uow, statement.company_id, statement.period_id
            )
            return state["source_digest"] == statement.snapshot_digest and not state["issues"]
        except (ClosingRunStale, ReportSourceStale, StateConflict):
            return False

    def detail(self, actor: Principal, company: UUID, identifier: UUID) -> dict[str, object]:
        with self.equity.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            statement = self._statement(uow, company, identifier)
            rows = list(
                uow.session.scalars(
                    select(StatementSetReviewModel)
                    .where(
                        StatementSetReviewModel.company_id == company,
                        StatementSetReviewModel.statement_id == identifier,
                    )
                    .order_by(StatementSetReviewModel.version)
                )
            )
            return {
                "status": rows[-1].status if rows else "NOT_REQUESTED",
                "version": rows[-1].version if rows else 0,
                "source_stale": not self._current(uow, statement),
                "events": [_row(row) for row in rows],
                "validation_status": "INTERNAL_VALIDATION_ONLY",
            }

    def transition(
        self,
        actor: Principal,
        company: UUID,
        identifier: UUID,
        expected_version: int,
        action: str,
        reason: str,
        key: str,
    ) -> dict[str, object]:
        targets = {
            "request-review": "REVIEW_REQUESTED",
            "approve": "APPROVED",
            "reject": "REJECTED",
        }
        if (
            action not in targets
            or expected_version < 0
            or not reason.strip()
            or len(reason) > 1000
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key)
        ):
            raise InvalidInput()
        with self.equity.factory() as uow:
            require_company(
                uow,
                actor,
                company,
                "financial_statement.generate"
                if action == "request-review"
                else "financial_statement.approve",
            )
            statement = self._statement(uow, company, identifier)
            uow.lock_period(company, statement.period_id)
            uow.lock_command(company, actor.user_id, "statement_set.review", key)
            fingerprint = digest((str(identifier), expected_version, action, reason))
            replay = uow.session.scalar(
                select(StatementSetReviewModel).where(
                    StatementSetReviewModel.company_id == company,
                    StatementSetReviewModel.actor_id == actor.user_id,
                    StatementSetReviewModel.idempotency_key == key,
                )
            )
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    raise StateConflict()
                return _row(replay)
            previous = latest_review(uow, company, identifier)
            if expected_version != (previous.version if previous else 0):
                raise VersionConflict()
            if action == "request-review":
                if previous is not None and previous.status != "REJECTED":
                    raise StateConflict()
                requester = actor.user_id
            else:
                if previous is None or previous.status != "REVIEW_REQUESTED":
                    raise StateConflict()
                requester = previous.requested_by
                if actor.user_id in {requester, statement.generated_by}:
                    raise StateConflict()
            if not self._current(uow, statement):
                raise ReportSourceStale()
            row = StatementSetReviewModel(
                id=uuid4(),
                company_id=company,
                statement_id=identifier,
                source_digest=statement.snapshot_digest,
                version=expected_version + 1,
                status=targets[action],
                actor_id=actor.user_id,
                requested_by=requester,
                reason=reason.strip(),
                idempotency_key=key,
                fingerprint=fingerprint,
                created_at=uow.now(),
            )
            uow.session.add(row)
            uow.session.flush()
            return _row(row)
