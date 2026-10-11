"""원본 행 복제 없이 승격 위치·거래 참조와 요청 재시도 기록을 보존합니다."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base


class ImportPromotionRowModel(Base):
    __tablename__ = "import_promotion_rows"
    __table_args__ = (
        UniqueConstraint("import_id", "sheet_index", "row_number"),
        UniqueConstraint("import_id", "source_id"),
        ForeignKeyConstraint(
            ["company_id", "import_id", "receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "transaction_id"],
            ["transactions.company_id", "transactions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("sheet_index >= 0 AND row_number >= 2", name="locator"),
        CheckConstraint("status IN ('CREATED','REUSED')", name="status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    import_id: Mapped[UUID] = mapped_column(index=True)
    receipt_id: Mapped[UUID] = mapped_column(index=True)
    sheet_index: Mapped[int]
    row_number: Mapped[int]
    source_id: Mapped[str] = mapped_column(String(100))
    row_digest: Mapped[str] = mapped_column(String(64))
    transaction_id: Mapped[UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20))
    review_code: Mapped[str | None] = mapped_column(String(40))
    promoted_at: Mapped[datetime]


class ImportPromotionCommandModel(Base):
    __tablename__ = "import_promotion_commands"
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "command_code", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "import_id", "receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("command_code = 'IMPORT_PROMOTE'", name="command"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    command_code: Mapped[str] = mapped_column(String(40), default="IMPORT_PROMOTE")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    import_id: Mapped[UUID] = mapped_column(index=True)
    receipt_id: Mapped[UUID] = mapped_column(index=True)
    created_at: Mapped[datetime]
