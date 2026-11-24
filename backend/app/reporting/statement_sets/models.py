from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey


class StatementSetRevisionModel(UUIDPrimaryKey, Base):
    __tablename__ = "statement_set_revisions"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    period_id: Mapped[UUID]
    statement_set_id: Mapped[UUID]
    balance_id: Mapped[UUID]
    income_id: Mapped[UUID]
    cash_id: Mapped[UUID]
    equity_id: Mapped[UUID]
    notes_id: Mapped[UUID]
    snapshot_digest: Mapped[str] = mapped_column(String(64))
    generated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    generated_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "period_id", "snapshot_digest"),
        *[
            ForeignKeyConstraint(
                ["company_id", column], [table + ".company_id", table + ".id"], ondelete="RESTRICT"
            )
            for column, table in (
                ("period_id", "accounting_periods"),
                ("statement_set_id", "financial_statement_sets"),
                ("balance_id", "financial_statements"),
                ("income_id", "financial_statements"),
                ("cash_id", "cash_flow_statements"),
                ("equity_id", "statement_of_changes_in_equity"),
                ("notes_id", "disclosure_instances"),
            )
        ],
    )


class StatementSetCommandModel(UUIDPrimaryKey, Base):
    __tablename__ = "statement_set_commands"

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    statement_id: Mapped[UUID]
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("company_id", "actor_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["statement_set_revisions.company_id", "statement_set_revisions.id"],
            ondelete="RESTRICT",
        ),
    )
