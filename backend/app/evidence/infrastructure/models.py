from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.evidence.domain.types import EvidenceType


class EvidenceModel(Base):
    __tablename__ = "evidences"
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        ForeignKeyConstraint(
            ["company_id", "storage_object_id", "sha256"],
            ["storage_objects.company_id", "storage_objects.id", "storage_objects.sha256"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "parent_evidence_id"],
            ["evidences.company_id", "evidences.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("parent_evidence_id IS NULL OR parent_evidence_id <> id", name="parent"),
        CheckConstraint(
            "evidence_type IN (" + ",".join(repr(t.value) for t in EvidenceType) + ")",
            name="type",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(30))
    source_type: Mapped[str] = mapped_column(String(30))
    source_system: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str] = mapped_column(String(100))
    storage_object_id: Mapped[UUID] = mapped_column(index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(100))
    original_filename: Mapped[str] = mapped_column(String(200))
    observed_at: Mapped[datetime]
    ingested_at: Mapped[datetime]
    created_at: Mapped[datetime]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    parent_evidence_id: Mapped[UUID | None] = mapped_column(index=True)
