"""Bookkeeper의 기간 질의를 기존 실행·단계·Tool 감사에 기록합니다.

Revision ID: 017_accounting_agent_queries
Revises: 016_financial_statements
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.database.types import MoneyNumeric

revision: str = "017_accounting_agent_queries"
down_revision: str | Sequence[str] | None = "016_financial_statements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("agent_runs", "transaction_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("agent_runs", sa.Column("period_id", sa.Uuid(), nullable=True))
    op.add_column("agent_runs", sa.Column("question_text", sa.String(500), nullable=True))
    op.add_column("agent_runs", sa.Column("answer_text", sa.String(2000), nullable=True))
    op.add_column("agent_runs", sa.Column("answer_amount", MoneyNumeric(), nullable=True))
    op.add_column("agent_runs", sa.Column("answer_resource_id", sa.Uuid(), nullable=True))
    op.add_column("agent_runs", sa.Column("answer_source_digest", sa.String(64), nullable=True))
    op.create_index("ix_agent_runs_period_id", "agent_runs", ["period_id"])
    op.create_foreign_key(
        "fk_agent_runs_company_period",
        "agent_runs",
        "accounting_periods",
        ["company_id", "period_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_agent_runs_query_or_transaction",
        "agent_runs",
        "(transaction_id IS NOT NULL AND period_id IS NULL AND question_text IS NULL) "
        "OR (transaction_id IS NULL AND period_id IS NOT NULL AND question_text IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_runs_query_or_transaction", "agent_runs", type_="check")
    op.drop_constraint("fk_agent_runs_company_period", "agent_runs", type_="foreignkey")
    op.drop_index("ix_agent_runs_period_id", table_name="agent_runs")
    for column in (
        "answer_source_digest",
        "answer_resource_id",
        "answer_amount",
        "answer_text",
        "question_text",
        "period_id",
    ):
        op.drop_column("agent_runs", column)
    op.alter_column("agent_runs", "transaction_id", existing_type=sa.Uuid(), nullable=False)
