from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class PeriodModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "accounting_periods"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    fiscal_year: Mapped[int]
    period_no: Mapped[int]
    start_date: Mapped[date]
    end_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(16), server_default=text("'OPEN'"))
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_year", "period_no"),
        Index("ix_accounting_periods_company_dates", "company_id", "start_date", "end_date"),
        CheckConstraint(
            "fiscal_year BETWEEN 1900 AND 9998 AND period_no BETWEEN 1 AND 12", name="period_number"
        ),
        CheckConstraint("start_date <= end_date", name="date_range"),
        CheckConstraint("status IN ('OPEN','CLOSED')", name="status"),
        CheckConstraint("version >= 1", name="version"),
        ExcludeConstraint(
            ("company_id", "="),
            (func.daterange(text("start_date"), text("end_date"), text("'[]'")), "&&"),
            name="ex_accounting_periods_date_range",
            using="gist",
        ),
    )
