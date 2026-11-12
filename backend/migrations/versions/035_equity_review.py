"""Append-only independent review for SCE snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "035_equity_review"
down_revision = "034_statement_comparatives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equity_review_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("statement_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "statement_id", "version"),
        sa.UniqueConstraint("company_id", "actor_id", "idempotency_key"),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["statement_of_changes_in_equity.company_id", "statement_of_changes_in_equity.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version > 0 AND length(trim(reason)) > 0", name="input"),
        sa.CheckConstraint("status IN ('REVIEW_REQUESTED','APPROVED','REJECTED')", name="status"),
        sa.CheckConstraint(
            "status = 'REVIEW_REQUESTED' OR actor_id <> requested_by", name="separation"
        ),
    )
    op.execute("""
    CREATE FUNCTION equity_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE snapshot_row record; prior_row record;
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Equity review is immutable' USING ERRCODE='23514';
      END IF;
      SELECT * INTO snapshot_row FROM statement_of_changes_in_equity
        WHERE company_id=NEW.company_id AND id=NEW.statement_id FOR UPDATE;
      IF NOT FOUND OR NEW.source_digest <> snapshot_row.snapshot_digest THEN
        RAISE EXCEPTION 'Equity source mismatch' USING ERRCODE='23514';
      END IF;
      SELECT * INTO prior_row FROM equity_review_events
        WHERE company_id=NEW.company_id AND statement_id=NEW.statement_id
        ORDER BY version DESC LIMIT 1;
      IF NEW.version <> COALESCE(prior_row.version, 0) + 1 THEN
        RAISE EXCEPTION 'Equity review version conflict' USING ERRCODE='23514';
      END IF;
      IF NEW.status='REVIEW_REQUESTED' THEN
        IF NEW.actor_id <> NEW.requested_by OR
           (prior_row.id IS NOT NULL AND prior_row.status <> 'REJECTED') THEN
          RAISE EXCEPTION 'Invalid review request' USING ERRCODE='23514';
        END IF;
      ELSIF prior_row.id IS NULL OR prior_row.status <> 'REVIEW_REQUESTED' OR
        NEW.requested_by <> prior_row.requested_by OR NEW.actor_id=NEW.requested_by OR
        NEW.actor_id=snapshot_row.generated_by THEN
        RAISE EXCEPTION 'Independent review required' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER equity_review_guard BEFORE INSERT OR UPDATE OR DELETE ON equity_review_events
    FOR EACH ROW EXECUTE FUNCTION equity_review_guard();
    """)


def downgrade() -> None:
    op.drop_table("equity_review_events")
    op.execute("DROP FUNCTION equity_review_guard()")
