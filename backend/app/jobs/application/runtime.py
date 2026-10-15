"""제품 실행 이력의 짧은 UoW와 접근 검증을 담당합니다."""

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID, uuid4

from app.companies.application.service import require_company
from app.contracts.access_errors import AuthorizationDenied, ResourceNotFound, VersionConflict
from app.identity.users.domain.entities import Principal
from app.jobs.application.contracts import RuntimeUnitOfWork
from app.jobs.domain.runtime import EventRead, RunRead, StepRead
from app.tools.contracts import ToolContext


class RuntimeAudit:
    def __init__(self, factory: Callable[[], RuntimeUnitOfWork]) -> None:
        self.factory = factory

    def create(
        self,
        actor: Principal,
        company: UUID,
        transaction: UUID,
        provider: str,
        model: str,
        key: str,
        fingerprint: str,
    ) -> RunRead:
        with self.factory() as uow:
            require_company(uow, actor, company, "journal.propose")
            return uow.runtime.create(
                actor, company, transaction, provider, model, key, fingerprint, uow.now()
            )

    def create_query(
        self,
        actor: Principal,
        company: UUID,
        period_id: UUID,
        question: str,
        provider: str,
        model: str,
        key: str,
        fingerprint: str,
    ) -> RunRead:
        with self.factory() as uow:
            require_company(uow, actor, company, "company.read")
            return uow.runtime.create(
                actor,
                company,
                None,
                provider,
                model,
                key,
                fingerprint,
                uow.now(),
                period_id,
                question,
            )

    def get(self, actor: Principal, company: UUID, run: UUID) -> RunRead:
        with self.factory() as uow:
            require_company(uow, actor, company, "company.read")
            value = uow.runtime.get(company, run)
            if value is None:
                raise ResourceNotFound()
            require_company(
                uow,
                actor,
                company,
                "period.read" if value.period_id is not None else "journal.read",
            )
            return value

    def claim(
        self, actor: Principal, company: UUID, run: UUID, expected_version: int | None = None
    ) -> bool:
        with self.factory() as uow:
            require_company(uow, actor, company, "company.read")
            value = uow.runtime.get(company, run, lock=True)
            if value is None:
                raise ResourceNotFound()
            if value.period_id is None:
                require_company(uow, actor, company, "journal.propose")
            if value.requested_by != actor.user_id:
                raise AuthorizationDenied()
            if expected_version is not None and value.version != expected_version:
                raise VersionConflict()
            return uow.runtime.claim(company, run, uuid4(), uow.now())

    def finish(
        self,
        context: ToolContext,
        status: str,
        stage: str,
        verdict: str | None = None,
        journal: UUID | None = None,
        error: str | None = None,
        answer_text: str | None = None,
        answer_amount: Decimal | None = None,
        answer_resource_id: UUID | None = None,
        answer_source_digest: str | None = None,
    ) -> None:
        assert context.run_id is not None
        with self.factory() as uow:
            uow.runtime.finish(
                context.company_id,
                context.run_id,
                status,
                stage,
                uow.now(),
                verdict,
                journal,
                error,
                answer_text,
                answer_amount,
                answer_resource_id,
                answer_source_digest,
            )

    def begin_step(self, context: ToolContext, node: str) -> UUID:
        assert context.run_id is not None
        with self.factory() as uow:
            return uow.runtime.begin_step(context.company_id, context.run_id, node, uow.now())

    def finish_step(self, context: ToolContext, status: str, error: str | None = None) -> None:
        assert context.run_id is not None and context.step_id is not None
        with self.factory() as uow:
            uow.runtime.finish_step(
                context.company_id, context.run_id, context.step_id, status, uow.now(), error
            )

    def record_tool(
        self,
        context: ToolContext,
        code: str,
        input_digest: str,
        output_digest: str,
        status: str,
        latency: int,
        error: str | None,
    ) -> None:
        if context.run_id is None:
            return
        with self.factory() as uow:
            uow.runtime.tool(
                context.company_id,
                context.run_id,
                context.step_id,
                code,
                input_digest,
                output_digest,
                status,
                latency,
                error,
                uow.now(),
            )

    def tool_started(self, context: ToolContext, code: str) -> None:
        if context.run_id is not None:
            with self.factory() as uow:
                uow.runtime.tool_started(context.company_id, context.run_id, code, uow.now())

    def steps(self, actor: Principal, company: UUID, run: UUID) -> list[StepRead]:
        self.get(actor, company, run)
        with self.factory() as uow:
            return uow.runtime.steps(company, run)

    def events(self, actor: Principal, company: UUID, run: UUID, after: int) -> list[EventRead]:
        self.get(actor, company, run)
        with self.factory() as uow:
            return uow.runtime.events(company, run, after)
