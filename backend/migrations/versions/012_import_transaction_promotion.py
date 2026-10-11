"""확정 가져오기의 거래 승격 결과와 재시도 참조를 추가합니다."""

from alembic import op
import sqlalchemy as sa

revision = "012_import_transaction_promotion"
down_revision = "011_accounting_dimensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("import_receipts", sa.Column("confirmed_version", sa.Integer(), nullable=True))
    op.add_column(
        "import_receipts", sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE import_receipts r SET confirmed_version = i.version FROM imports i WHERE i.id = r.import_id"
    )
    op.alter_column("import_receipts", "confirmed_version", nullable=False)
    op.create_check_constraint(
        op.f("ck_import_receipts_confirmed_version"), "import_receipts", "confirmed_version >= 1"
    )
    op.drop_constraint(op.f("ck_import_receipts_counts"), "import_receipts", type_="check")
    op.create_check_constraint(
        op.f("ck_import_receipts_counts"),
        "import_receipts",
        "transaction_count >= 0 AND counterparty_count = 0 AND evidence_count >= 1",
    )
    op.create_unique_constraint(
        op.f("uq_import_receipts_company_id_import_id_id"),
        "import_receipts",
        ["company_id", "import_id", "id"],
    )
    # 배포된 기존 정규 거래 대상 접수는 승격 대기 상태로 명시합니다.
    op.execute(
        "UPDATE imports SET status='CONFIRMED', completed_at=NULL WHERE target_context='TRANSACTION_CANONICAL' AND status='COMPLETED' AND id IN (SELECT import_id FROM import_receipts WHERE transaction_count=0)"
    )
    op.execute(
        "UPDATE import_receipts SET status='CONFIRMED' WHERE import_id IN (SELECT id FROM imports WHERE target_context='TRANSACTION_CANONICAL' AND status='CONFIRMED')"
    )
    op.create_table(
        "import_promotion_rows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("sheet_index", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("row_digest", sa.String(64), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("review_code", sa.String(40)),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("import_id", "sheet_index", "row_number"),
        sa.UniqueConstraint("import_id", "source_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "import_id", "receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "transaction_id"],
            ["transactions.company_id", "transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "sheet_index >= 0 AND row_number >= 2", name=op.f("ck_import_promotion_rows_locator")
        ),
        sa.CheckConstraint(
            "status IN ('CREATED','REUSED')", name=op.f("ck_import_promotion_rows_status")
        ),
    )
    op.create_table(
        "import_promotion_commands",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("command_code", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "actor_id", "command_code", "idempotency_key"),
        sa.ForeignKeyConstraint(
            ["company_id", "import_id", "receipt_id"],
            ["import_receipts.company_id", "import_receipts.import_id", "import_receipts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "command_code = 'IMPORT_PROMOTE'", name=op.f("ck_import_promotion_commands_command")
        ),
    )
    for table, columns in {
        "import_promotion_rows": ["company_id", "import_id", "receipt_id", "transaction_id"],
        "import_promotion_commands": ["company_id", "actor_id", "import_id", "receipt_id"],
    }.items():
        for column in columns:
            op.create_index(op.f(f"ix_{table}_{column}"), table, [column])


def downgrade() -> None:
    # 거래 정본을 삭제하거나 완료된 승격 이력을 지우는 다운그레이드는 허용하지 않습니다.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM import_promotion_rows)")):
        raise RuntimeError(
            "승격 이력이 있는 DB는 백업 복구 또는 후속 수정 migration을 사용해 주세요."
        )
    op.drop_table("import_promotion_commands")
    op.drop_table("import_promotion_rows")
    op.drop_constraint(
        op.f("uq_import_receipts_company_id_import_id_id"), "import_receipts", type_="unique"
    )
    op.drop_constraint(
        op.f("ck_import_receipts_confirmed_version"), "import_receipts", type_="check"
    )
    op.drop_constraint(op.f("ck_import_receipts_counts"), "import_receipts", type_="check")
    op.create_check_constraint(
        op.f("ck_import_receipts_counts"),
        "import_receipts",
        "transaction_count = 0 AND counterparty_count = 0 AND evidence_count >= 1",
    )
    op.execute(
        "UPDATE imports SET status='COMPLETED', completed_at=confirmed_at WHERE status='CONFIRMED' AND target_context='TRANSACTION_CANONICAL'"
    )
    op.execute("UPDATE import_receipts SET status='COMPLETED' WHERE status='CONFIRMED'")
    op.drop_column("import_receipts", "promoted_at")
    op.drop_column("import_receipts", "confirmed_version")
