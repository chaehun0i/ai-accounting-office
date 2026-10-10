from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base


class TenantModel(Base):
    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','DISABLED')", name="status"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CompanyModel(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "business_number"),
        CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="status"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("taxpayer_type IN ('CORPORATION','INDIVIDUAL')", name="taxpayer_type"),
        CheckConstraint("business_number ~ '^[0-9]{10}$'", name="business_number"),
        CheckConstraint(
            "corporation_number IS NULL OR corporation_number ~ '^[0-9]{13}$'",
            name="corporation_number",
        ),
        Index("ix_companies_tenant_status", "tenant_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), index=True
    )
    company_name: Mapped[str] = mapped_column(String(200))
    business_number: Mapped[str] = mapped_column(String(10))
    timezone: Mapped[str] = mapped_column(String(40), server_default="Asia/Seoul")
    corporation_number: Mapped[str | None] = mapped_column(String(13))
    taxpayer_type: Mapped[str] = mapped_column(String(16))
    opening_date: Mapped[date]
    address: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), server_default="ACTIVE")
    version: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RoleModel(Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class PermissionModel(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"
    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="RESTRICT"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("permissions.code", ondelete="RESTRICT"), primary_key=True, index=True
    )


class MembershipModel(Base):
    __tablename__ = "company_memberships"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id"),
        CheckConstraint("status IN ('ACTIVE','REVOKED')", name="status"),
        CheckConstraint("(status = 'REVOKED') = (revoked_at IS NOT NULL)", name="revocation"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_company_memberships_company_status", "company_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), server_default="ACTIVE")
    joined_at: Mapped[datetime] = mapped_column(server_default=func.now())
    revoked_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(server_default="1")


class InvitationModel(Base):
    __tablename__ = "company_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "invited_by"],
            ["company_memberships.company_id", "company_memberships.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('PENDING','ACCEPTED','REVOKED','EXPIRED')", name="status"),
        CheckConstraint("email = lower(btrim(email))", name="normalized_email"),
        CheckConstraint("expires_at > created_at", name="expiry"),
        CheckConstraint(
            "(status = 'ACCEPTED') = (accepted_by IS NOT NULL AND accepted_at IS NOT NULL)",
            name="acceptance",
        ),
        Index(
            "uq_company_invitations_pending",
            "company_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("ix_company_invitations_inviter", "company_id", "invited_by"),
        Index("ix_company_invitations_company_status", "company_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="RESTRICT"), index=True
    )
    invite_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING")
    invited_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(index=True)
    accepted_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    accepted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
