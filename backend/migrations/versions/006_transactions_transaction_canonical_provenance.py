"""거래 정본과 출처 관계형 구조

리비전: 006_transactions
이전 리비전: 005_onboarding_data_exchange
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa


revision: str = "006_transactions"
down_revision: str | Sequence[str] | None = "005_onboarding_data_exchange"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 회사 범위와 출처 무결성을 명시적인 제약으로 생성합니다.
    op.create_table(
        "transactions",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("accounting_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column(
            "tax_amount",
            sa.Numeric(19, 4),
            nullable=False,
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("direction", sa.String(length=12), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("counterparty_id", sa.Uuid(), nullable=True),
        sa.Column("import_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("currency_code = 'KRW'", name=op.f("ck_transactions_currency")),
        sa.CheckConstraint(
            "direction IN ('INFLOW','OUTFLOW')", name=op.f("ck_transactions_direction")
        ),
        sa.CheckConstraint(
            "status IN ('RECEIVED','NORMALIZED','READY_FOR_ACCOUNTING','NEEDS_INFORMATION','DUPLICATE_REVIEW','EXCLUDED')",
            name=op.f("ck_transactions_status"),
        ),
        sa.CheckConstraint(
            "amount > 0 AND tax_amount >= 0 AND tax_amount <= amount",
            name=op.f("ck_transactions_amount"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_transactions_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "counterparty_id"],
            ["counterparties.company_id", "counterparties.id"],
            name=op.f("fk_transactions_company_id_counterparty_id_counterparties"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidences.company_id", "evidences.id"],
            name=op.f("fk_transactions_company_id_evidence_id_evidences"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "import_id"],
            ["imports.company_id", "imports.id"],
            name=op.f("fk_transactions_company_id_import_id_imports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_transactions_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_transactions_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_transactions_company_id_id")),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_id",
            name=op.f("uq_transactions_company_id_source_system_source_id"),
        ),
    )
    op.create_index(
        op.f("ix_transactions_company_id"), "transactions", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_transactions_counterparty_id"), "transactions", ["counterparty_id"], unique=False
    )
    op.create_index(
        op.f("ix_transactions_created_by"), "transactions", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_transactions_evidence_id"), "transactions", ["evidence_id"], unique=False
    )
    op.create_index(op.f("ix_transactions_import_id"), "transactions", ["import_id"], unique=False)
    op.create_index(op.f("ix_transactions_status"), "transactions", ["status"], unique=False)
    op.create_index(
        op.f("ix_transactions_transaction_date"), "transactions", ["transaction_date"], unique=False
    )


def downgrade() -> None:
    # 회사 범위와 출처 무결성을 명시적인 제약으로 생성합니다.
    op.drop_index(op.f("ix_transactions_transaction_date"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_status"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_import_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_evidence_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_created_by"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_counterparty_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_company_id"), table_name="transactions")
    op.drop_table("transactions")
