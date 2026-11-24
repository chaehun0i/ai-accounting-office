"""Pin the five supported statements without changing accounting snapshots."""

import re
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.disclosures.models import DisclosureInstanceModel
from app.reporting.disclosures.service import DisclosureService
from app.reporting.equity.review import latest_review
from app.reporting.equity.service import _row
from app.reporting.statement_sets.models import StatementSetCommandModel, StatementSetRevisionModel


class StatementSetService(DisclosureService):
    def collect(self, uow: CashFlowUnitOfWork, company: UUID, period_id: UUID) -> dict[str, Any]:
        source, source_issues = self._sources(uow, company, period_id)
        issues = list(source_issues)
        note = None
        if source:
            note = uow.session.scalar(
                select(DisclosureInstanceModel)
                .where(
                    DisclosureInstanceModel.company_id == company,
                    DisclosureInstanceModel.period_id == period_id,
                    DisclosureInstanceModel.source_digest == source["source_digest"],
                    DisclosureInstanceModel.status == "APPROVED",
                )
                .order_by(DisclosureInstanceModel.revision.desc())
                .limit(1)
            )
            if note is None:
                issues.append("APPROVED_NOTES_REQUIRED")
            review = latest_review(uow, company, source["equity"].id)
            if (
                review is None
                or review.status != "APPROVED"
                or review.source_digest != source["equity"].snapshot_digest
            ):
                issues.append("EQUITY_APPROVAL_REQUIRED")
        identity = None
        members = {}
        if source and note:
            members = {
                "statement_set_id": source["statement_set_id"],
                "balance_id": source["balance"].id,
                "income_id": source["income"].id,
                "cash_id": source["cash"].id,
                "equity_id": source["equity"].id,
                "notes_id": note.id,
            }
            identity = digest(
                (
                    source["source_digest"],
                    str(note.id),
                    note.revision,
                    note.version,
                    note.reconciliation_digest,
                    [(k, str(v)) for k, v in members.items()],
                )
            )
        return {
            "period_id": period_id,
            "status": "BLOCKED" if issues else "READY",
            "issues": issues,
            "source_digest": identity,
            "members": members,
            "validation_status": "INTERNAL_VALIDATION_ONLY",
        }

    def readiness(self, actor: Principal, company: UUID, period_id: UUID) -> dict[str, Any]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return self.collect(uow, company, period_id)

    def generate(
        self, actor: Principal, company: UUID, period_id: UUID, key: str
    ) -> dict[str, object]:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            uow.lock_period(company, period_id)
            uow.lock_command(company, actor.user_id, "statement_set.generate", key)
            replay = uow.session.scalar(
                select(StatementSetCommandModel).where(
                    StatementSetCommandModel.company_id == company,
                    StatementSetCommandModel.actor_id == actor.user_id,
                    StatementSetCommandModel.idempotency_key == key,
                )
            )
            fingerprint = digest(str(period_id))
            if replay:
                if replay.fingerprint != fingerprint:
                    raise StateConflict()
                existing = uow.session.get(StatementSetRevisionModel, replay.statement_id)
                assert existing is not None
                return _row(existing)
            state = self.collect(uow, company, period_id)
            if state["issues"]:
                raise StateConflict()
            row = uow.session.scalar(
                select(StatementSetRevisionModel).where(
                    StatementSetRevisionModel.company_id == company,
                    StatementSetRevisionModel.period_id == period_id,
                    StatementSetRevisionModel.snapshot_digest == state["source_digest"],
                )
            )
            if row is None:
                row = StatementSetRevisionModel(
                    id=uuid4(),
                    company_id=company,
                    period_id=period_id,
                    **state["members"],
                    snapshot_digest=state["source_digest"],
                    generated_by=actor.user_id,
                    generated_at=uow.now(),
                )
                uow.session.add(row)
                uow.session.flush()
            uow.session.add(
                StatementSetCommandModel(
                    id=uuid4(),
                    company_id=company,
                    actor_id=actor.user_id,
                    idempotency_key=key,
                    fingerprint=fingerprint,
                    statement_id=row.id,
                    created_at=uow.now(),
                )
            )
            uow.session.flush()
            return _row(row)

    def list(self, actor: Principal, company: UUID, period_id: UUID) -> list[dict[str, object]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return [
                _row(row)
                for row in uow.session.scalars(
                    select(StatementSetRevisionModel)
                    .where(
                        StatementSetRevisionModel.company_id == company,
                        StatementSetRevisionModel.period_id == period_id,
                    )
                    .order_by(StatementSetRevisionModel.generated_at.desc())
                )
            ]

    def detail(self, actor: Principal, company: UUID, identifier: UUID) -> dict[str, Any]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            row = uow.session.scalar(
                select(StatementSetRevisionModel).where(
                    StatementSetRevisionModel.company_id == company,
                    StatementSetRevisionModel.id == identifier,
                )
            )
            if row is None:
                raise ResourceNotFound()
            state = self.collect(uow, company, row.period_id)
            return {
                **_row(row),
                "source_stale": state["source_digest"] != row.snapshot_digest
                or bool(state["issues"]),
                "issues": state["issues"],
            }
