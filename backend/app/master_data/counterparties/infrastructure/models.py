from datetime import date
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
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class CounterpartyModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "counterparties"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    counterparty_code: Mapped[str | None] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str] = mapped_column(String(200))
    normalized_legal_name: Mapped[str] = mapped_column(String(200))
    business_number: Mapped[str | None] = mapped_column(String(10))
    corporation_number: Mapped[str | None] = mapped_column(String(13))
    counterparty_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'ACTIVE'"))
    default_currency_code: Mapped[str] = mapped_column(String(3))
    payment_term_id: Mapped[UUID | None] = mapped_column(index=True)
    __table_args__ = (
        UniqueConstraint("company_id", "counterparty_code"),
        UniqueConstraint("company_id", "id"),
        ForeignKeyConstraint(
            ["company_id", "payment_term_id"],
            ["payment_terms.company_id", "payment_terms.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_counterparties_company_id_payment_term_id", "company_id", "payment_term_id"),
        Index("ix_counterparties_company_id_status", "company_id", "status"),
        Index("ix_counterparties_company_id_display_name", "company_id", "display_name"),
        Index(
            "ix_counterparties_company_id_normalized_legal_name",
            "company_id",
            "normalized_legal_name",
        ),
        Index(
            "uq_counterparties_company_business",
            "company_id",
            "business_number",
            unique=True,
            postgresql_where=text("business_number IS NOT NULL"),
        ),
        CheckConstraint(
            "business_number IS NULL OR business_number ~ '^[0-9]{10}$'", name="business_number"
        ),
        CheckConstraint(
            "corporation_number IS NULL OR corporation_number ~ '^[0-9]{13}$'",
            name="corporation_number",
        ),
        CheckConstraint("counterparty_type IN ('BUSINESS','INDIVIDUAL','OTHER')", name="type"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE','BLOCKED')", name="status"),
        CheckConstraint(
            "default_currency_code IN ('KRW','USD','EUR','JPY','GBP','CAD','AU"
            "D','CHF','CNY','SGD','HKD')",
            name="currency",
        ),
        CheckConstraint("version >= 1", name="version"),
    )


class CounterpartyRoleModel(UUIDPrimaryKey, Base):
    __tablename__ = "counterparty_roles"
    counterparty_id: Mapped[UUID] = mapped_column(
        ForeignKey("counterparties.id", ondelete="RESTRICT"), index=True
    )
    role_code: Mapped[str] = mapped_column(String(32))
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    __table_args__ = (
        CheckConstraint(
            "role_code IN ('CUSTOMER','SUPPLIER','PAYEE','TAX_COUNTERPARTY')", name="role"
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from <= effective_to", name="date_range"
        ),
        ExcludeConstraint(
            ("counterparty_id", "="),
            ("role_code", "="),
            (func.daterange(text("effective_from"), text("effective_to"), text("'[]'")), "&&"),
            name="ex_counterparty_role_effective_range",
            using="gist",
        ),
    )


class CounterpartyContactModel(UUIDPrimaryKey, Base):
    __tablename__ = "counterparty_contacts"
    counterparty_id: Mapped[UUID] = mapped_column(
        ForeignKey("counterparties.id", ondelete="RESTRICT"), index=True
    )
    contact_type: Mapped[str] = mapped_column(String(24))
    contact_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    is_primary: Mapped[bool] = mapped_column(server_default=text("false"))
    __table_args__ = (
        CheckConstraint("contact_type IN ('GENERAL','BILLING','SALES')", name="type"),
        Index(
            "uq_counterparty_primary_contact",
            "counterparty_id",
            "contact_type",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )


class CounterpartyAddressModel(UUIDPrimaryKey, Base):
    __tablename__ = "counterparty_addresses"
    counterparty_id: Mapped[UUID] = mapped_column(
        ForeignKey("counterparties.id", ondelete="RESTRICT"), index=True
    )
    address_type: Mapped[str] = mapped_column(String(24))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    address_line1: Mapped[str] = mapped_column(String(300))
    address_line2: Mapped[str | None] = mapped_column(String(300))
    is_primary: Mapped[bool] = mapped_column(server_default=text("false"))
    __table_args__ = (
        CheckConstraint("address_type IN ('REGISTERED','BILLING','SHIPPING')", name="type"),
        Index(
            "uq_counterparty_primary_address",
            "counterparty_id",
            "address_type",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )


class CounterpartyBankReferenceModel(UUIDPrimaryKey, Base):
    __tablename__ = "counterparty_bank_refs"
    counterparty_id: Mapped[UUID] = mapped_column(
        ForeignKey("counterparties.id", ondelete="RESTRICT"), index=True
    )
    bank_code: Mapped[str] = mapped_column(String(20))
    account_alias: Mapped[str] = mapped_column(String(100))
    external_token: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'ACTIVE'"))
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint(
            "external_token ~ '^vault:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9"
            "a-f]{4}-[0-9a-f]{12}$'",
            name="vault_reference",
        ),
    )
