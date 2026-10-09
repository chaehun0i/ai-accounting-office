from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base


class StorageObjectModel(Base):
    __tablename__ = "storage_objects"
    __table_args__ = (
        UniqueConstraint("company_id", "id", "sha256"),
        UniqueConstraint("storage_provider", "storage_key"),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 2000000", name="size"),
        CheckConstraint("status IN ('AVAILABLE','RETAINED','DELETED')", name="status"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    storage_provider: Mapped[str] = mapped_column(String(30))
    storage_key: Mapped[str] = mapped_column(String(100))
    original_filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]
