"""사용자·리프레시 세션·인증 보안 이벤트를 생성합니다.

리비전: 001_identity
이전 리비전: db_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_identity"
down_revision: str | Sequence[str] | None = "db_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 관계형 제약과 인덱스를 명시합니다.
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DISABLED','REVOKED')", name=op.f("ck_users_status")
        ),
        sa.CheckConstraint("email = lower(btrim(email))", name=op.f("ck_users_normalized_email")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_family_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=32), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=True),
        sa.Column("ip_prefix", sa.String(length=64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'REVOKED') = (revoked_at IS NOT NULL)",
            name=op.f("ck_refresh_sessions_revocation"),
        ),
        sa.CheckConstraint(
            "(status = 'ROTATED') = (rotated_at IS NOT NULL) OR status = 'REVOKED'",
            name=op.f("ck_refresh_sessions_rotation"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','ROTATED','REVOKED','EXPIRED')",
            name=op.f("ck_refresh_sessions_status"),
        ),
        sa.CheckConstraint("expires_at > issued_at", name=op.f("ck_refresh_sessions_expiry")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_sessions_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_sessions")),
        sa.UniqueConstraint("jti_hash", name=op.f("uq_refresh_sessions_jti_hash")),
        sa.UniqueConstraint(
            "refresh_token_hash", name=op.f("uq_refresh_sessions_refresh_token_hash")
        ),
    )
    op.create_index("ix_refresh_sessions_expiry", "refresh_sessions", ["expires_at"], unique=False)
    op.create_index(
        "ix_refresh_sessions_family", "refresh_sessions", ["session_family_id"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_sessions_user_id"), "refresh_sessions", ["user_id"], unique=False
    )
    op.create_table(
        "identity_security_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("session_family_id", sa.Uuid(), nullable=True),
        sa.Column("event_code", sa.String(length=32), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=True),
        sa.Column("ip_prefix", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_code IN ('REGISTER_ATTEMPT','LOGIN_SUCCEEDED','LOGIN_FAILED',"
            "'REFRESH_ATTEMPT','REFRESH_SUCCEEDED','REFRESH_REUSED','SESSION_REVOKED',"
            "'SESSION_FAMILY_REVOKED','ALL_SESSIONS_REVOKED')",
            name=op.f("ck_identity_security_events_event_code"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["refresh_sessions.id"],
            name=op.f("fk_identity_security_events_session_id_refresh_sessions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_identity_security_events_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_security_events")),
    )
    op.create_index(
        "ix_identity_security_events_email_time",
        "identity_security_events",
        ["email_hash", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_identity_security_events_ip_time",
        "identity_security_events",
        ["ip_prefix", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_identity_security_events_session_family_id"),
        "identity_security_events",
        ["session_family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_identity_security_events_session_id"),
        "identity_security_events",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_identity_security_events_user_id"),
        "identity_security_events",
        ["user_id"],
        unique=False,
    )
    # 마이그레이션 정의 끝.


def downgrade() -> None:
    # 관계형 제약과 인덱스를 명시합니다.
    op.drop_index(
        op.f("ix_identity_security_events_user_id"), table_name="identity_security_events"
    )
    op.drop_index(
        op.f("ix_identity_security_events_session_id"), table_name="identity_security_events"
    )
    op.drop_index(
        op.f("ix_identity_security_events_session_family_id"), table_name="identity_security_events"
    )
    op.drop_index("ix_identity_security_events_ip_time", table_name="identity_security_events")
    op.drop_index("ix_identity_security_events_email_time", table_name="identity_security_events")
    op.drop_table("identity_security_events")
    op.drop_index(op.f("ix_refresh_sessions_user_id"), table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_family", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_expiry", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
    op.drop_table("users")
    # 마이그레이션 정의 끝.
