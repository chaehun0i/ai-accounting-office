from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class PaymentTermModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "payment_terms"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    term_code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    due_rule_type: Mapped[str] = mapped_column(String(32))
    due_days: Mapped[int] = mapped_column(server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "term_code"),
        CheckConstraint(
            "due_rule_type IN ('IMMEDIATE','NET_DAYS','MONTH_END_PLUS_DAYS')", name="due_rule"
        ),
        CheckConstraint(
            "due_days BETWEEN 0 AND 3650 AND (due_rule_type <> 'IMMEDIATE' OR due_days=0)",
            name="due_days",
        ),
        CheckConstraint("version >= 1", name="version"),
    )
