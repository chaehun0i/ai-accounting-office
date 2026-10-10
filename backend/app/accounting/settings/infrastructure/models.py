from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import Timestamped, UUIDPrimaryKey, Versioned


class AccountingSettingsModel(UUIDPrimaryKey, Timestamped, Versioned, Base):
    __tablename__ = "accounting_settings"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), unique=True, index=True
    )
    functional_currency_code: Mapped[str] = mapped_column(String(3))
    fiscal_year_start_month: Mapped[int]
    accounting_framework_code: Mapped[str] = mapped_column(String(20), server_default="K_GAAP")
    reporting_taxonomy_code: Mapped[str] = mapped_column(String(20), server_default="STANDARD")
    journal_number_prefix: Mapped[str] = mapped_column(String(10))
    numbering_reset_policy: Mapped[str] = mapped_column(String(16))
    allow_manual_journal: Mapped[bool]
    __table_args__ = (
        CheckConstraint(
            "functional_currency_code IN ('KRW','USD','EUR','JPY','GBP','CAD',"
            "'AUD','CHF','CNY','SGD','HKD')",
            name="currency",
        ),
        CheckConstraint("fiscal_year_start_month BETWEEN 1 AND 12", name="fiscal_month"),
        CheckConstraint("journal_number_prefix ~ '^[A-Z][A-Z0-9]{0,9}$'", name="prefix"),
        CheckConstraint("numbering_reset_policy IN ('FISCAL_YEAR','NEVER')", name="reset_policy"),
        CheckConstraint("version >= 1", name="version"),
    )
