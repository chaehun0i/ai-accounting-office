from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class JournalSequenceModel(UUIDPrimaryKey, Base):
    __tablename__ = "journal_sequences"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    fiscal_year: Mapped[int]
    sequence_key: Mapped[str] = mapped_column(String(40))
    last_number: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_year", "sequence_key"),
        CheckConstraint("fiscal_year=0 OR fiscal_year BETWEEN 1900 AND 9998", name="fiscal_year"),
        CheckConstraint("last_number >= 0", name="last_number"),
    )
