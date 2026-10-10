from dataclasses import asdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.domain.entities import Approval
from app.approvals.infrastructure.models import ApprovalModel, AuditEventModel, IdempotencyModel
from app.intake.domain.errors import IdempotencyConflict


class GovernanceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def approval(self, company: UUID, resource: UUID) -> Approval | None:
        row = self.session.scalar(
            select(ApprovalModel)
            .where(ApprovalModel.company_id == company, ApprovalModel.id == resource)
            .with_for_update()
        )
        return (
            Approval(**{k: getattr(row, k) for k in Approval.__dataclass_fields__}) if row else None
        )

    def save_approval(self, value: Approval) -> None:
        row = self.session.scalar(
            select(ApprovalModel)
            .where(ApprovalModel.company_id == value.company_id, ApprovalModel.id == value.id)
            .with_for_update()
        )
        if row:
            for k, v in asdict(value).items():
                setattr(row, k, v)
        else:
            self.session.add(ApprovalModel(**asdict(value)))
        self.session.flush()

    def replay(
        self, company: UUID, actor: UUID, command: str, key: str, fingerprint: str
    ) -> UUID | None:
        row = self.session.scalar(
            select(IdempotencyModel).where(
                IdempotencyModel.company_id == company,
                IdempotencyModel.actor_id == actor,
                IdempotencyModel.command_code == command,
                IdempotencyModel.idempotency_key == key,
            )
        )
        if row and row.request_fingerprint != fingerprint:
            raise IdempotencyConflict()
        return row.journal_id if row else None

    def record(
        self,
        company: UUID,
        actor: UUID,
        command: str,
        key: str,
        fingerprint: str,
        journal: UUID,
        version: int,
        now: datetime,
    ) -> None:
        self.session.add(
            IdempotencyModel(
                id=uuid4(),
                company_id=company,
                actor_id=actor,
                command_code=command,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                status="SUCCEEDED",
                journal_id=journal,
                result_version=version,
                http_status=200,
                created_at=now,
                completed_at=now,
            )
        )
        self.session.flush()

    def audit(
        self,
        company: UUID,
        actor: UUID,
        command: str,
        journal: UUID,
        request_id: str,
        before: str,
        after: str,
        now: datetime,
    ) -> None:
        self.session.add(
            AuditEventModel(
                id=uuid4(),
                company_id=company,
                actor_id=actor,
                journal_id=journal,
                action_code=command,
                result_code="SUCCEEDED",
                request_id=request_id,
                before_digest=before,
                after_digest=after,
                occurred_at=now,
            )
        )
        self.session.flush()
