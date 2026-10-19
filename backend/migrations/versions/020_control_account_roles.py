"""Relational company control account role mapping and approval requests.

Revision ID: 020_control_account_roles
Revises: 019_account_changes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_control_account_roles"
down_revision: str | Sequence[str] | None = "019_account_changes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "control_account_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("company_id", "role"),
        sa.UniqueConstraint("company_id", "account_id"),
        sa.CheckConstraint(
            "role IN ('AR','AP','TAX_INPUT','TAX_OUTPUT',"
            "'BANK_CASH','CARD_CLEARING','CARD_PAYABLE')",
            name="ck_control_account_mappings_role",
        ),
        sa.CheckConstraint("version >= 1", name="ck_control_account_mappings_version"),
    )
    # Existing BANK/CARD assignments are explicit data. Never infer AR/AP from account names.
    op.execute(
        sa.text("""
        INSERT INTO control_account_mappings (id, company_id, role, account_id, version, updated_at)
        SELECT gen_random_uuid(), company_id, control_account_type, id, 1, CURRENT_TIMESTAMP
        FROM chart_of_accounts a
        WHERE control_account_type IS NOT NULL
          AND (SELECT count(*) FROM chart_of_accounts b
               WHERE b.company_id=a.company_id
                 AND b.control_account_type=a.control_account_type) = 1
    """)
    )
    # Versioned template IDs are explicit catalog evidence. Pick one primary
    # AR/AP account per company; legacy secondary accounts remain historical.
    op.execute(
        sa.text("""
        WITH candidates AS (
            SELECT a.company_id, a.id AS account_id,
                   CASE WHEN t.account_code IN ('1100','1101') THEN 'AR' ELSE 'AP' END AS role,
                   row_number() OVER (
                       PARTITION BY a.company_id,
                           CASE WHEN t.account_code IN ('1100','1101') THEN 'AR' ELSE 'AP' END
                       ORDER BY CASE t.account_code
                           WHEN '1100' THEN 0 WHEN '2010' THEN 0 ELSE 1 END, a.id
                   ) AS priority
            FROM chart_of_accounts a
            JOIN coa_template_accounts t ON t.id = a.template_account_id
            WHERE t.account_code IN ('1100','1101','2010','2011')
              AND a.status = 'ACTIVE' AND a.posting_allowed
        )
        INSERT INTO control_account_mappings (id, company_id, role, account_id, version, updated_at)
        SELECT gen_random_uuid(), company_id, role, account_id, 1, CURRENT_TIMESTAMP
        FROM candidates WHERE priority = 1
    """)
    )
    # Seed the remaining roles only when a versioned template account is
    # unambiguous and has no other explicit mapping. CARD_CLEARING has no
    # canonical template identity and remains unset.
    op.execute(
        sa.text("""
        WITH candidates AS (
            SELECT a.company_id, a.id AS account_id,
                   CASE t.account_code
                       WHEN '1200' THEN 'TAX_INPUT'
                       WHEN '2100' THEN 'TAX_OUTPUT'
                       WHEN '1020' THEN 'BANK_CASH'
                       WHEN '2020' THEN 'CARD_PAYABLE'
                   END AS role
            FROM chart_of_accounts a
            JOIN coa_template_accounts t ON t.id = a.template_account_id
            WHERE t.account_code IN ('1200','2100','1020','2020')
              AND a.status = 'ACTIVE' AND a.posting_allowed
        ), unambiguous AS (
            SELECT *, count(*) OVER (PARTITION BY company_id, role) AS role_count
            FROM candidates
        )
        INSERT INTO control_account_mappings (id, company_id, role, account_id, version, updated_at)
        SELECT gen_random_uuid(), c.company_id, c.role, c.account_id, 1, CURRENT_TIMESTAMP
        FROM unambiguous c
        WHERE c.role_count = 1
          AND NOT EXISTS (
              SELECT 1 FROM control_account_mappings m
              WHERE m.company_id=c.company_id
                AND (m.role=c.role OR m.account_id=c.account_id)
          )
    """)
    )
    op.create_table(
        "control_account_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("current_account_id", sa.Uuid()),
        sa.Column("target_account_id", sa.Uuid(), nullable=False),
        sa.Column("expected_mapping_version", sa.Integer(), nullable=False),
        sa.Column("expected_target_account_version", sa.Integer(), nullable=False),
        sa.Column("impact_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("approver_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("executed_by_id", sa.Uuid()),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("execution_key", sa.String(100)),
        sa.Column("execution_fingerprint", sa.String(64)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["executed_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "current_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "target_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("company_id", "requester_id", "request_key"),
        sa.CheckConstraint(
            "role IN ('AR','AP','TAX_INPUT','TAX_OUTPUT',"
            "'BANK_CASH','CARD_CLEARING','CARD_PAYABLE')",
            name="ck_control_account_requests_role",
        ),
        sa.CheckConstraint(
            "status IN ('REQUESTED','APPROVED','REJECTED','EXECUTED')",
            name="ck_control_account_requests_status",
        ),
        sa.CheckConstraint(
            "expected_mapping_version >= 0 AND expected_target_account_version >= 1 "
            "AND version >= 1",
            name="ck_control_account_requests_versions",
        ),
    )
    op.create_index(
        "ix_control_account_requests_company_created",
        "control_account_requests",
        ["company_id", "created_at"],
    )
    op.create_index(
        "uq_control_account_execution_key",
        "control_account_requests",
        ["company_id", "executed_by_id", "execution_key"],
        unique=True,
        postgresql_where=sa.text("execution_key IS NOT NULL"),
    )
    op.create_table(
        "control_account_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("before_account_id", sa.Uuid()),
        sa.Column("after_account_id", sa.Uuid()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["control_account_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "before_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "after_account_id"],
            ["chart_of_accounts.company_id", "chart_of_accounts.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_control_account_events_company_request",
        "control_account_events",
        ["company_id", "request_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_control_account_events_company_request", table_name="control_account_events")
    op.drop_table("control_account_events")
    op.drop_index(
        "ix_control_account_requests_company_created", table_name="control_account_requests"
    )
    op.drop_index("uq_control_account_execution_key", table_name="control_account_requests")
    op.drop_table("control_account_requests")
    op.drop_table("control_account_mappings")
