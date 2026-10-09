from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base


class RefreshSessionModel(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','ROTATED','REVOKED','EXPIRED')", name="status"),
        CheckConstraint("expires_at > issued_at", name="expiry"),
        CheckConstraint(
            "(status = 'ROTATED') = (rotated_at IS NOT NULL) OR status = 'REVOKED'", name="rotation"
        ),
        CheckConstraint("(status = 'REVOKED') = (revoked_at IS NOT NULL)", name="revocation"),
        Index("ix_refresh_sessions_family", "session_family_id"),
        Index("ix_refresh_sessions_expiry", "expires_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    session_family_id: Mapped[UUID]
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    jti_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default="ACTIVE")
    issued_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    rotated_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    revoke_reason: Mapped[str | None] = mapped_column(String(32))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))
    ip_prefix: Mapped[str | None] = mapped_column(String(64))
    last_seen_at: Mapped[datetime | None]


class IdentitySecurityEventModel(Base):
    __tablename__ = "identity_security_events"
    __table_args__ = (
        CheckConstraint(
            "event_code IN ('REGISTER_ATTEMPT','LOGIN_SUCCEEDED','LOGIN_FAILED',"
            "'REFRESH_ATTEMPT','REFRESH_SUCCEEDED','REFRESH_REUSED','SESSION_REVOKED',"
            "'SESSION_FAMILY_REVOKED','ALL_SESSIONS_REVOKED')",
            name="event_code",
        ),
        Index("ix_identity_security_events_email_time", "email_hash", "occurred_at"),
        Index("ix_identity_security_events_ip_time", "ip_prefix", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="RESTRICT"), index=True
    )
    session_family_id: Mapped[UUID | None] = mapped_column(index=True)
    event_code: Mapped[str] = mapped_column(String(32))
    email_hash: Mapped[str | None] = mapped_column(String(64))
    ip_prefix: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[UUID | None]
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
