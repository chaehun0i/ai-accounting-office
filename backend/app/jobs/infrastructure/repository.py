"""짧은 row lock으로 실행 소유권과 감사 순서를 보호합니다."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.identity.users.domain.entities import Principal
from app.intake.domain.errors import IdempotencyConflict
from app.jobs.domain.runtime import EventRead, RunRead, StepRead
from app.jobs.infrastructure.models import (
    AgentRunModel,
    AgentStepModel,
    JobEventModel,
    JobModel,
    ToolExecutionModel,
)


class RuntimeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _run(self, company: UUID, run: UUID, lock: bool = False) -> AgentRunModel | None:
        query = select(AgentRunModel).where(
            AgentRunModel.company_id == company, AgentRunModel.id == run
        )
        return self.session.scalar(query.with_for_update() if lock else query)

    def get(self, company: UUID, run: UUID, *, lock: bool = False) -> RunRead | None:
        value = self._run(company, run, lock)
        return RunRead.model_validate(value) if value else None

    def create(
        self,
        actor: Principal,
        company: UUID,
        transaction: UUID | None,
        provider: str,
        model: str,
        key: str,
        fingerprint: str,
        now: datetime,
        period_id: UUID | None = None,
        question_text: str | None = None,
    ) -> RunRead:
        # 회사 행을 잠가 같은 회사/사용자/키의 최초 생성 경쟁을 직렬화합니다.
        from app.companies.infrastructure.models import CompanyModel

        self.session.scalar(
            select(CompanyModel.id).where(CompanyModel.id == company).with_for_update()
        )
        old = self.session.scalar(
            select(AgentRunModel).where(
                AgentRunModel.company_id == company,
                AgentRunModel.requested_by == actor.user_id,
                AgentRunModel.idempotency_key == key,
            )
        )
        if old:
            if old.input_digest != fingerprint:
                raise IdempotencyConflict()
            return RunRead.model_validate(old)
        job_id, run_id = uuid4(), uuid4()
        self.session.add(
            JobModel(
                id=job_id,
                company_id=company,
                requested_by=actor.user_id,
                job_type="ACCOUNTING_QUERY" if question_text is not None else "BOOKKEEPER",
                status="PENDING",
                stage="PENDING",
                progress_percent=0,
                correlation_id=run_id,
                attempt_count=0,
                max_attempts=3,
                available_at=now,
                created_at=now,
            )
        )
        self.session.flush()
        run = AgentRunModel(
            id=run_id,
            company_id=company,
            requested_by=actor.user_id,
            job_id=job_id,
            transaction_id=transaction,
            period_id=period_id,
            question_text=question_text,
            principal_session_id=actor.session_id,
            graph_name="bookkeeper",
            graph_version="2" if question_text is not None else "1",
            agent_type="BOOKKEEPER",
            prompt_version="1",
            tool_registry_version="1",
            provider_code=provider,
            model_code=model,
            graph_thread_id=str(run_id),
            checkpoint_namespace="",
            status="PENDING",
            current_stage="PENDING",
            version=1,
            input_digest=fingerprint,
            idempotency_key=key,
            created_at=now,
        )
        self.session.add(run)
        self.session.flush()
        return RunRead.model_validate(run)

    def claim(self, company: UUID, run: UUID, worker: UUID, now: datetime) -> bool:
        value = self._run(company, run, True)
        assert value is not None
        job = self.session.scalar(
            select(JobModel)
            .where(JobModel.company_id == company, JobModel.id == value.job_id)
            .with_for_update()
        )
        assert job is not None
        if job.lease_expires_at and job.lease_expires_at > now:
            return False
        if value.status in ("COMPLETED", "BLOCKED") or job.attempt_count >= job.max_attempts:
            return False
        job.lease_owner, job.lease_expires_at = worker, now + timedelta(minutes=5)
        job.heartbeat_at = now
        job.attempt_count += 1
        job.status, job.started_at = "RUNNING", job.started_at or now
        value.status, value.started_at = "RUNNING", value.started_at or now
        value.version += 1
        self._event(value, "RUN_STARTED", "PLANNING", now)
        return True

    def _event(
        self, run: AgentRunModel, event: str, stage: str, now: datetime, code: str | None = None
    ) -> None:
        self.session.flush()
        seq = (
            self.session.scalar(
                select(func.coalesce(func.max(JobEventModel.event_seq), 0)).where(
                    JobEventModel.company_id == run.company_id, JobEventModel.job_id == run.job_id
                )
            )
            or 0
        )
        self.session.add(
            JobEventModel(
                company_id=run.company_id,
                job_id=run.job_id,
                event_seq=seq + 1,
                event_type=event,
                stage=stage,
                message_code=code,
                created_at=now,
            )
        )

    def finish(
        self,
        company: UUID,
        run: UUID,
        status: str,
        stage: str,
        now: datetime,
        verdict: str | None = None,
        journal: UUID | None = None,
        error: str | None = None,
        answer_text: str | None = None,
        answer_amount: Decimal | None = None,
        answer_resource_id: UUID | None = None,
        answer_source_digest: str | None = None,
    ) -> None:
        value = self._run(company, run, True)
        assert value is not None
        value.status, value.current_stage = status, stage
        value.controller_verdict, value.error_code = verdict, error
        value.pending_action = "REVIEW_PROPOSAL" if status == "WAITING_FOR_INPUT" else None
        value.result_journal_id = journal
        if answer_text is not None:
            value.answer_text = answer_text
            value.answer_amount = answer_amount
            value.answer_resource_id = answer_resource_id
            value.answer_source_digest = answer_source_digest
        value.version += 1
        terminal = status in ("COMPLETED", "FAILED", "BLOCKED")
        value.finished_at = now if terminal else None
        job = self.session.get(JobModel, value.job_id)
        assert job is not None
        job.status, job.stage = status, stage
        job.lease_owner, job.lease_expires_at = None, None
        job.progress_percent = (
            100 if status == "COMPLETED" else 80 if status == "WAITING_FOR_INPUT" else 0
        )
        job.finished_at, job.error_code = value.finished_at, error
        if verdict:
            self._event(value, "CONTROLLER_VERDICT", stage, now, verdict)
        self._event(value, status, stage, now, error)

    def begin_step(self, company: UUID, run: UUID, node: str, now: datetime) -> UUID:
        value = self._run(company, run, True)
        assert value is not None
        no = (
            self.session.scalar(
                select(func.coalesce(func.max(AgentStepModel.step_no), 0)).where(
                    AgentStepModel.company_id == company, AgentStepModel.agent_run_id == run
                )
            )
            or 0
        )
        step = uuid4()
        self.session.add(
            AgentStepModel(
                id=step,
                company_id=company,
                agent_run_id=run,
                step_no=no + 1,
                node_name=node,
                status="RUNNING",
                started_at=now,
            )
        )
        value.current_stage = node
        self._event(value, "NODE_STARTED", node, now)
        return step

    def finish_step(
        self,
        company: UUID,
        run: UUID,
        step: UUID,
        status: str,
        now: datetime,
        error: str | None = None,
    ) -> None:
        value = self.session.scalar(
            select(AgentStepModel).where(
                AgentStepModel.company_id == company,
                AgentStepModel.agent_run_id == run,
                AgentStepModel.id == step,
            )
        )
        assert value is not None
        value.status, value.finished_at, value.error_code = status, now, error

    def tool(
        self,
        company: UUID,
        run: UUID,
        step: UUID | None,
        code: str,
        input_digest: str,
        output_digest: str,
        status: str,
        latency: int,
        error: str | None,
        now: datetime,
    ) -> None:
        value = self._run(company, run, True)
        assert value is not None
        self.session.add(
            ToolExecutionModel(
                company_id=company,
                agent_run_id=run,
                agent_step_id=step,
                tool_code=code,
                tool_version="1",
                status=status,
                permission_decision="DENIED" if error == "AUTHORIZATION_DENIED" else "ALLOWED",
                input_digest=input_digest,
                output_digest=output_digest,
                latency_ms=latency,
                error_code=error,
                created_at=now,
            )
        )
        self._event(value, "TOOL_COMPLETED", code, now, error)

    def tool_started(self, company: UUID, run: UUID, code: str, now: datetime) -> None:
        value = self._run(company, run, True)
        assert value is not None
        job = self.session.get(JobModel, value.job_id)
        assert job is not None
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(minutes=5)
        self._event(value, "TOOL_STARTED", code, now)

    def steps(self, company: UUID, run: UUID) -> list[StepRead]:
        return [
            StepRead.model_validate(r)
            for r in self.session.scalars(
                select(AgentStepModel)
                .where(AgentStepModel.company_id == company, AgentStepModel.agent_run_id == run)
                .order_by(AgentStepModel.step_no)
            )
        ]

    def events(self, company: UUID, run: UUID, after: int) -> list[EventRead]:
        value = self._run(company, run)
        assert value is not None
        return [
            EventRead.model_validate(r)
            for r in self.session.scalars(
                select(JobEventModel)
                .where(
                    JobEventModel.company_id == company,
                    JobEventModel.job_id == value.job_id,
                    JobEventModel.event_seq > after,
                )
                .order_by(JobEventModel.event_seq)
                .limit(1000)
            )
        ]
