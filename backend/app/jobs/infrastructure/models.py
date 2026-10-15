"""실행 제품 정본은 명시적인 열과 회사 복합 외래키로 저장합니다."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDPrimaryKey, Versioned
from app.core.database.types import MoneyNumeric


class JobModel(UUIDPrimaryKey, Base):
    __tablename__ = "jobs"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    requested_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), index=True)
    stage: Mapped[str] = mapped_column(String(80))
    progress_percent: Mapped[int]
    correlation_id: Mapped[UUID]
    attempt_count: Mapped[int]
    max_attempts: Mapped[int]
    available_at: Mapped[datetime]
    lease_owner: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None]
    heartbeat_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="progress"),
        CheckConstraint("attempt_count >= 0 AND max_attempts BETWEEN 1 AND 5", name="attempts"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','WAITING_FOR_INPUT','COMPLETED','FAILED','BLOCKED')",
            name="status",
        ),
    )


class AgentRunModel(UUIDPrimaryKey, Versioned, Base):
    __tablename__ = "agent_runs"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    requested_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    job_id: Mapped[UUID] = mapped_column(index=True, unique=True)
    transaction_id: Mapped[UUID | None] = mapped_column(index=True)
    period_id: Mapped[UUID | None] = mapped_column(index=True)
    question_text: Mapped[str | None] = mapped_column(String(500))
    answer_text: Mapped[str | None] = mapped_column(String(2000))
    answer_amount: Mapped[Decimal | None] = mapped_column(MoneyNumeric())
    answer_resource_id: Mapped[UUID | None]
    answer_source_digest: Mapped[str | None] = mapped_column(String(64))
    principal_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="RESTRICT")
    )
    graph_name: Mapped[str] = mapped_column(String(40))
    graph_version: Mapped[str] = mapped_column(String(20))
    agent_type: Mapped[str] = mapped_column(String(40))
    prompt_version: Mapped[str] = mapped_column(String(20))
    tool_registry_version: Mapped[str] = mapped_column(String(20))
    provider_code: Mapped[str] = mapped_column(String(30))
    model_code: Mapped[str] = mapped_column(String(100))
    graph_thread_id: Mapped[str] = mapped_column(String(100), unique=True)
    checkpoint_namespace: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), index=True)
    current_stage: Mapped[str] = mapped_column(String(80))
    controller_verdict: Mapped[str | None] = mapped_column(String(10))
    pending_action: Mapped[str | None] = mapped_column(String(60))
    result_journal_id: Mapped[UUID | None] = mapped_column(index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    input_digest: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    __table_args__ = (
        UniqueConstraint("company_id", "id"),
        UniqueConstraint("company_id", "requested_by", "idempotency_key"),
        ForeignKeyConstraint(
            ["company_id", "job_id"], ["jobs.company_id", "jobs.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["company_id", "transaction_id"],
            ["transactions.company_id", "transactions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(transaction_id IS NOT NULL AND period_id IS NULL AND question_text IS NULL) "
            "OR (transaction_id IS NULL AND period_id IS NOT NULL AND question_text IS NOT NULL)",
            name="query_or_transaction",
        ),
        ForeignKeyConstraint(
            ["company_id", "result_journal_id"],
            ["journal_entries.company_id", "journal_entries.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','WAITING_FOR_INPUT','COMPLETED','FAILED','BLOCKED')",
            name="status",
        ),
        CheckConstraint(
            "controller_verdict IS NULL OR controller_verdict IN ('PASS','REVIEW','BLOCK')",
            name="verdict",
        ),
    )


class AgentStepModel(UUIDPrimaryKey, Base):
    __tablename__ = "agent_steps"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    agent_run_id: Mapped[UUID] = mapped_column(index=True)
    step_no: Mapped[int]
    node_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    __table_args__ = (
        UniqueConstraint("company_id", "id", "agent_run_id"),
        UniqueConstraint("agent_run_id", "step_no"),
        ForeignKeyConstraint(
            ["company_id", "agent_run_id"],
            ["agent_runs.company_id", "agent_runs.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("step_no > 0", name="step_no"),
        CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','WAITING_FOR_INPUT')", name="status"
        ),
    )


class ToolExecutionModel(UUIDPrimaryKey, Base):
    __tablename__ = "tool_executions"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    agent_run_id: Mapped[UUID] = mapped_column(index=True)
    agent_step_id: Mapped[UUID | None] = mapped_column(index=True)
    tool_code: Mapped[str] = mapped_column(String(100))
    tool_version: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    permission_decision: Mapped[str] = mapped_column(String(20))
    input_digest: Mapped[str] = mapped_column(String(64))
    output_digest: Mapped[str] = mapped_column(String(64))
    latency_ms: Mapped[int]
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime]
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "agent_run_id"],
            ["agent_runs.company_id", "agent_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "agent_step_id", "agent_run_id"],
            ["agent_steps.company_id", "agent_steps.id", "agent_steps.agent_run_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("latency_ms >= 0", name="latency"),
        CheckConstraint("status IN ('SUCCEEDED','FAILED')", name="status"),
    )


class JobEventModel(UUIDPrimaryKey, Base):
    __tablename__ = "job_events"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    job_id: Mapped[UUID] = mapped_column(index=True)
    event_seq: Mapped[int]
    event_type: Mapped[str] = mapped_column(String(60))
    stage: Mapped[str] = mapped_column(String(80))
    message_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint("job_id", "event_seq"),
        ForeignKeyConstraint(
            ["company_id", "job_id"], ["jobs.company_id", "jobs.id"], ondelete="RESTRICT"
        ),
        CheckConstraint("event_seq > 0", name="sequence"),
    )
