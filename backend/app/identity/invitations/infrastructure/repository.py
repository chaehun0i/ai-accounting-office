from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.companies.infrastructure.models import CompanyModel, InvitationModel, TenantModel
from app.identity.invitations.application.contracts import Invitation


class InvitationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _entity(row: InvitationModel | None) -> Invitation | None:
        return (
            None
            if row is None
            else Invitation(**{key: getattr(row, key) for key in Invitation.__dataclass_fields__})
        )

    def pending(self, company_id: UUID, email: str, now: datetime) -> bool:
        self.session.execute(
            update(InvitationModel)
            .where(
                InvitationModel.company_id == company_id,
                InvitationModel.email == email,
                InvitationModel.status == "PENDING",
                InvitationModel.expires_at <= now,
            )
            .values(status="EXPIRED")
        )
        return (
            self.session.scalar(
                select(InvitationModel.id).where(
                    InvitationModel.company_id == company_id,
                    InvitationModel.email == email,
                    InvitationModel.status == "PENDING",
                )
            )
            is not None
        )

    def add(self, invitation: Invitation) -> None:
        self.session.add(InvitationModel(**asdict(invitation)))
        self.session.flush()

    def for_token(self, token_hash: str, email: str) -> Invitation | None:
        # 초대 수락은 인증된 이메일에 결합된 일회용 capability 조회입니다.
        row = self.session.scalar(
            select(InvitationModel)
            .join(CompanyModel)
            .join(TenantModel)
            .where(
                InvitationModel.invite_token_hash == token_hash,
                InvitationModel.email == email,
                CompanyModel.status == "ACTIVE",
                TenantModel.status == "ACTIVE",
            )
            .with_for_update(of=[InvitationModel, CompanyModel])
        )
        return self._entity(row)

    def get(self, company_id: UUID, invitation_id: UUID) -> Invitation | None:
        return self._entity(
            self.session.scalar(
                select(InvitationModel)
                .where(
                    InvitationModel.company_id == company_id,
                    InvitationModel.id == invitation_id,
                )
                .with_for_update()
            )
        )

    def save(self, invitation: Invitation) -> None:
        self.session.execute(
            update(InvitationModel)
            .where(
                InvitationModel.company_id == invitation.company_id,
                InvitationModel.id == invitation.id,
            )
            .values(**asdict(invitation))
        )
