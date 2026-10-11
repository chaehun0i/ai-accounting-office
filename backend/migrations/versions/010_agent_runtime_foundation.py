"""Agent 실행 감사 정본과 격리된 framework schema를 추가합니다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010_agent_runtime_foundation"
down_revision: str | Sequence[str] | None = "009_finance_subledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA agent_checkpoints")
    op.create_table(
        "jobs",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','WAITING_FOR_INPUT','COMPLETED','FAILED','BLOCKED')",
            name=op.f("ck_jobs_status"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 5", name=op.f("ck_jobs_attempts")
        ),
        sa.CheckConstraint("progress_percent BETWEEN 0 AND 100", name=op.f("ck_jobs_progress")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_jobs_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_jobs_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_jobs_company_id_id")),
    )
    op.create_index(op.f("ix_jobs_company_id"), "jobs", ["company_id"], unique=False)
    op.create_index(op.f("ix_jobs_requested_by"), "jobs", ["requested_by"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_table(
        "job_events",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("message_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("event_seq > 0", name=op.f("ck_job_events_sequence")),
        sa.ForeignKeyConstraint(
            ["company_id", "job_id"],
            ["jobs.company_id", "jobs.id"],
            name=op.f("fk_job_events_company_id_job_id_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_job_events_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_events")),
        sa.UniqueConstraint("job_id", "event_seq", name=op.f("uq_job_events_job_id_event_seq")),
    )
    op.create_index(op.f("ix_job_events_company_id"), "job_events", ["company_id"], unique=False)
    op.create_index(op.f("ix_job_events_job_id"), "job_events", ["job_id"], unique=False)
    op.create_table(
        "agent_runs",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("principal_session_id", sa.Uuid(), nullable=False),
        sa.Column("graph_name", sa.String(length=40), nullable=False),
        sa.Column("graph_version", sa.String(length=20), nullable=False),
        sa.Column("agent_type", sa.String(length=40), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("tool_registry_version", sa.String(length=20), nullable=False),
        sa.Column("provider_code", sa.String(length=30), nullable=False),
        sa.Column("model_code", sa.String(length=100), nullable=False),
        sa.Column("graph_thread_id", sa.String(length=100), nullable=False),
        sa.Column("checkpoint_namespace", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_stage", sa.String(length=80), nullable=False),
        sa.Column("controller_verdict", sa.String(length=10), nullable=True),
        sa.Column("pending_action", sa.String(length=60), nullable=True),
        sa.Column("result_journal_id", sa.Uuid(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "controller_verdict IS NULL OR controller_verdict IN ('PASS','REVIEW','BLOCK')",
            name=op.f("ck_agent_runs_verdict"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','WAITING_FOR_INPUT','COMPLETED','FAILED','BLOCKED')",
            name=op.f("ck_agent_runs_status"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_agent_runs_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "job_id"],
            ["jobs.company_id", "jobs.id"],
            name=op.f("fk_agent_runs_company_id_job_id_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "result_journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            name=op.f("fk_agent_runs_company_id_result_journal_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "transaction_id"],
            ["transactions.company_id", "transactions.id"],
            name=op.f("fk_agent_runs_company_id_transaction_id_transactions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_agent_runs_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["principal_session_id"],
            ["refresh_sessions.id"],
            name=op.f("fk_agent_runs_principal_session_id_refresh_sessions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_agent_runs_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
        sa.UniqueConstraint("company_id", "id", name=op.f("uq_agent_runs_company_id_id")),
        sa.UniqueConstraint(
            "company_id",
            "requested_by",
            "idempotency_key",
            name=op.f("uq_agent_runs_company_id_requested_by_idempotency_key"),
        ),
        sa.UniqueConstraint("graph_thread_id", name=op.f("uq_agent_runs_graph_thread_id")),
    )
    op.create_index(op.f("ix_agent_runs_company_id"), "agent_runs", ["company_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_job_id"), "agent_runs", ["job_id"], unique=True)
    op.create_index(
        op.f("ix_agent_runs_requested_by"), "agent_runs", ["requested_by"], unique=False
    )
    op.create_index(
        op.f("ix_agent_runs_result_journal_id"), "agent_runs", ["result_journal_id"], unique=False
    )
    op.create_index(op.f("ix_agent_runs_status"), "agent_runs", ["status"], unique=False)
    op.create_index(
        op.f("ix_agent_runs_transaction_id"), "agent_runs", ["transaction_id"], unique=False
    )
    op.create_table(
        "agent_steps",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("node_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','WAITING_FOR_INPUT')",
            name=op.f("ck_agent_steps_status"),
        ),
        sa.CheckConstraint("step_no > 0", name=op.f("ck_agent_steps_step_no")),
        sa.ForeignKeyConstraint(
            ["company_id", "agent_run_id"],
            ["agent_runs.company_id", "agent_runs.id"],
            name=op.f("fk_agent_steps_company_id_agent_run_id_agent_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_agent_steps_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_steps")),
        sa.UniqueConstraint(
            "agent_run_id", "step_no", name=op.f("uq_agent_steps_agent_run_id_step_no")
        ),
        sa.UniqueConstraint(
            "company_id",
            "id",
            "agent_run_id",
            name=op.f("uq_agent_steps_company_id_id_agent_run_id"),
        ),
    )
    op.create_index(
        op.f("ix_agent_steps_agent_run_id"), "agent_steps", ["agent_run_id"], unique=False
    )
    op.create_index(op.f("ix_agent_steps_company_id"), "agent_steps", ["company_id"], unique=False)
    op.create_table(
        "tool_executions",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("agent_step_id", sa.Uuid(), nullable=True),
        sa.Column("tool_code", sa.String(length=100), nullable=False),
        sa.Column("tool_version", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("permission_decision", sa.String(length=20), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("output_digest", sa.String(length=64), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED','FAILED')", name=op.f("ck_tool_executions_status")
        ),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_tool_executions_latency")),
        sa.ForeignKeyConstraint(
            ["company_id", "agent_run_id"],
            ["agent_runs.company_id", "agent_runs.id"],
            name=op.f("fk_tool_executions_company_id_agent_run_id_agent_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "agent_step_id", "agent_run_id"],
            ["agent_steps.company_id", "agent_steps.id", "agent_steps.agent_run_id"],
            name=op.f("fk_tool_executions_company_id_agent_step_id_agent_run_id_agent_steps"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_tool_executions_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_executions")),
    )
    op.create_index(
        op.f("ix_tool_executions_agent_run_id"), "tool_executions", ["agent_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_tool_executions_agent_step_id"), "tool_executions", ["agent_step_id"], unique=False
    )
    op.create_index(
        op.f("ix_tool_executions_company_id"), "tool_executions", ["company_id"], unique=False
    )
    # 도구 실행과 진행 이벤트는 append-only 감사 기록입니다.
    op.execute("""CREATE FUNCTION reject_runtime_audit_mutation() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'runtime audit is append only'; END; $$""")
    for table in ("tool_executions", "job_events"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_runtime_audit_mutation()"
        )


def downgrade() -> None:
    # 실행 중인 업무에서 downgrade하지 않습니다. checkpoint 보존은 별도 운영 정책입니다.
    op.drop_index(op.f("ix_tool_executions_company_id"), table_name="tool_executions")
    op.drop_index(op.f("ix_tool_executions_agent_step_id"), table_name="tool_executions")
    op.drop_index(op.f("ix_tool_executions_agent_run_id"), table_name="tool_executions")
    op.drop_table("tool_executions")
    op.drop_index(op.f("ix_agent_steps_company_id"), table_name="agent_steps")
    op.drop_index(op.f("ix_agent_steps_agent_run_id"), table_name="agent_steps")
    op.drop_table("agent_steps")
    op.drop_index(op.f("ix_agent_runs_transaction_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_status"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_result_journal_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_requested_by"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_job_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_company_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_job_events_job_id"), table_name="job_events")
    op.drop_index(op.f("ix_job_events_company_id"), table_name="job_events")
    op.drop_table("job_events")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_requested_by"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_company_id"), table_name="jobs")
    op.drop_table("jobs")
    op.execute("DROP FUNCTION reject_runtime_audit_mutation()")
    op.execute("DROP SCHEMA agent_checkpoints CASCADE")
