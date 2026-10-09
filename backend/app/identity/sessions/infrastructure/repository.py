from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.contracts.access_errors import RateLimited
from app.core.security import digest
from app.identity.sessions.domain.entities import RefreshSession, RequestFacts
from app.identity.sessions.infrastructure.models import (
    IdentitySecurityEventModel,
    RefreshSessionModel,
)


class SessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID, session_id: UUID) -> RefreshSession | None:
        row = self.session.scalar(
            select(RefreshSessionModel).where(
                RefreshSessionModel.id == session_id,
                RefreshSessionModel.user_id == user_id,
            )
        )
        return (
            None
            if row is None
            else RefreshSession(
                **{key: getattr(row, key) for key in RefreshSession.__dataclass_fields__}
            )
        )

    def add(self, session: RefreshSession) -> None:
        self.session.add(RefreshSessionModel(**asdict(session)))
        self.session.flush()

    def save(self, session: RefreshSession) -> None:
        self.session.execute(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.id == session.id,
                RefreshSessionModel.user_id == session.user_id,
            )
            .values(**asdict(session))
        )

    def revoke(
        self,
        user_id: UUID,
        now: datetime,
        reason: str,
        *,
        family_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> None:
        query = update(RefreshSessionModel).where(
            RefreshSessionModel.user_id == user_id,
            RefreshSessionModel.revoked_at.is_(None),
        )
        if family_id is not None:
            query = query.where(RefreshSessionModel.session_family_id == family_id)
        if session_id is not None:
            query = query.where(RefreshSessionModel.id == session_id)
        self.session.execute(query.values(status="REVOKED", revoked_at=now, revoke_reason=reason))


class SecurityEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        code: str,
        facts: RequestFacts,
        *,
        user_id: UUID | None = None,
        session: RefreshSession | None = None,
        email_hash: str | None = None,
    ) -> None:
        self.session.add(
            IdentitySecurityEventModel(
                id=uuid4(),
                event_code=code,
                user_id=user_id,
                session_id=session.id if session else None,
                session_family_id=session.session_family_id if session else None,
                email_hash=email_hash,
                ip_prefix=facts.ip_prefix,
                request_id=facts.request_id,
            )
        )
        self.session.flush()

    def limit(
        self, action: str, facts: RequestFacts, now: datetime, email_hash: str | None = None
    ) -> None:
        # 같은 전송원의 동시 시도도 DB 잠금으로 직렬화합니다.
        key = int(digest(f"{action}:{facts.ip_prefix}")[:15], 16)
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        events = IdentitySecurityEventModel
        codes = ["LOGIN_FAILED", "LOGIN_SUCCEEDED"] if action == "login" else [action]
        count = (
            self.session.scalar(
                select(func.count())
                .select_from(events)
                .where(
                    events.ip_prefix == facts.ip_prefix,
                    events.event_code.in_(codes),
                    events.occurred_at > now - timedelta(minutes=1),
                )
            )
            or 0
        )
        if count >= (20 if action == "REGISTER_ATTEMPT" else 60):
            raise RateLimited()
        if action in {"login", "REGISTER_ATTEMPT"} and email_hash:
            key = int(digest(f"email:{email_hash}")[:15], 16)
            self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            failures = (
                self.session.scalar(
                    select(func.count())
                    .select_from(events)
                    .where(
                        events.email_hash == email_hash,
                        events.event_code == "LOGIN_FAILED",
                        events.occurred_at > now - timedelta(minutes=15),
                    )
                )
                or 0
            )
            if action == "login" and failures >= 10:
                raise RateLimited()
