"""테넌트·회사·역할·권한·멤버십·초대를 생성합니다.

리비전: 002_tenant_company_rbac
이전 리비전: 001_identity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_tenant_company_rbac"
down_revision: str | Sequence[str] | None = "001_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 명시적인 관계형 제약과 인덱스를 적용합니다.
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_permissions")),
    )
    op.create_table(
        "roles",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_roles")),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
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
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name=op.f("ck_tenants_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("business_number", sa.String(length=10), nullable=False),
        sa.Column("corporation_number", sa.String(length=13), nullable=True),
        sa.Column("taxpayer_type", sa.String(length=16), nullable=False),
        sa.Column("opening_date", sa.Date(), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
            "business_number ~ '^[0-9]{10}$'", name=op.f("ck_companies_business_number")
        ),
        sa.CheckConstraint(
            "corporation_number IS NULL OR corporation_number ~ '^[0-9]{13}$'",
            name=op.f("ck_companies_corporation_number"),
        ),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name=op.f("ck_companies_status")),
        sa.CheckConstraint(
            "taxpayer_type IN ('CORPORATION','INDIVIDUAL')", name=op.f("ck_companies_taxpayer_type")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_companies_version")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_companies_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint(
            "tenant_id", "business_number", name=op.f("uq_companies_tenant_id_business_number")
        ),
    )
    op.create_index(op.f("ix_companies_tenant_id"), "companies", ["tenant_id"], unique=False)
    op.create_index(
        "ix_companies_tenant_status", "companies", ["tenant_id", "status"], unique=False
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_code", sa.String(length=32), nullable=False),
        sa.Column("permission_code", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["permissions.code"],
            name=op.f("fk_role_permissions_permission_code_permissions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["roles.code"],
            name=op.f("fk_role_permissions_role_code_roles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("role_code", "permission_code", name=op.f("pk_role_permissions")),
    )
    op.create_index(
        op.f("ix_role_permissions_permission_code"),
        "role_permissions",
        ["permission_code"],
        unique=False,
    )
    op.create_table(
        "company_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "(status = 'REVOKED') = (revoked_at IS NOT NULL)",
            name=op.f("ck_company_memberships_revocation"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','REVOKED')", name=op.f("ck_company_memberships_status")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_company_memberships_version")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_memberships_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["roles.code"],
            name=op.f("fk_company_memberships_role_code_roles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_company_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_memberships")),
        sa.UniqueConstraint(
            "company_id", "user_id", name=op.f("uq_company_memberships_company_id_user_id")
        ),
    )
    op.create_index(
        op.f("ix_company_memberships_company_id"),
        "company_memberships",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_memberships_company_status",
        "company_memberships",
        ["company_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_memberships_role_code"), "company_memberships", ["role_code"], unique=False
    )
    op.create_index(
        op.f("ix_company_memberships_user_id"), "company_memberships", ["user_id"], unique=False
    )
    op.create_table(
        "company_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role_code", sa.String(length=32), nullable=False),
        sa.Column("invite_token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'ACCEPTED') = (accepted_by IS NOT NULL AND accepted_at IS NOT NULL)",
            name=op.f("ck_company_invitations_acceptance"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','ACCEPTED','REVOKED','EXPIRED')",
            name=op.f("ck_company_invitations_status"),
        ),
        sa.CheckConstraint(
            "email = lower(btrim(email))", name=op.f("ck_company_invitations_normalized_email")
        ),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_company_invitations_expiry")),
        sa.ForeignKeyConstraint(
            ["accepted_by"],
            ["users.id"],
            name=op.f("fk_company_invitations_accepted_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "invited_by"],
            ["company_memberships.company_id", "company_memberships.user_id"],
            name=op.f("fk_company_invitations_company_id_invited_by_company_memberships"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_invitations_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_company_invitations_invited_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["roles.code"],
            name=op.f("fk_company_invitations_role_code_roles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_invitations")),
        sa.UniqueConstraint(
            "invite_token_hash", name=op.f("uq_company_invitations_invite_token_hash")
        ),
    )
    op.create_index(
        op.f("ix_company_invitations_accepted_by"),
        "company_invitations",
        ["accepted_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_invitations_company_id"),
        "company_invitations",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_invitations_company_status",
        "company_invitations",
        ["company_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_invitations_expires_at"),
        "company_invitations",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_invitations_invited_by"),
        "company_invitations",
        ["invited_by"],
        unique=False,
    )
    op.create_index(
        "ix_company_invitations_inviter",
        "company_invitations",
        ["company_id", "invited_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_invitations_role_code"), "company_invitations", ["role_code"], unique=False
    )
    op.create_index(
        "uq_company_invitations_pending",
        "company_invitations",
        ["company_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    # 마이그레이션 정의 끝.


def downgrade() -> None:
    # 명시적인 관계형 제약과 인덱스를 적용합니다.
    op.drop_index(
        "uq_company_invitations_pending",
        table_name="company_invitations",
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.drop_index(op.f("ix_company_invitations_role_code"), table_name="company_invitations")
    op.drop_index("ix_company_invitations_inviter", table_name="company_invitations")
    op.drop_index(op.f("ix_company_invitations_invited_by"), table_name="company_invitations")
    op.drop_index(op.f("ix_company_invitations_expires_at"), table_name="company_invitations")
    op.drop_index("ix_company_invitations_company_status", table_name="company_invitations")
    op.drop_index(op.f("ix_company_invitations_company_id"), table_name="company_invitations")
    op.drop_index(op.f("ix_company_invitations_accepted_by"), table_name="company_invitations")
    op.drop_table("company_invitations")
    op.drop_index(op.f("ix_company_memberships_user_id"), table_name="company_memberships")
    op.drop_index(op.f("ix_company_memberships_role_code"), table_name="company_memberships")
    op.drop_index("ix_company_memberships_company_status", table_name="company_memberships")
    op.drop_index(op.f("ix_company_memberships_company_id"), table_name="company_memberships")
    op.drop_table("company_memberships")
    op.drop_index(op.f("ix_role_permissions_permission_code"), table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_companies_tenant_status", table_name="companies")
    op.drop_index(op.f("ix_companies_tenant_id"), table_name="companies")
    op.drop_table("companies")
    op.drop_table("tenants")
    op.drop_table("roles")
    op.drop_table("permissions")
    # 마이그레이션 정의 끝.
