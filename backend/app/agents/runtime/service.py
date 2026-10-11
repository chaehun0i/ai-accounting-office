"""짧은 제품 트랜잭션과 긴 Graph 실행을 분리합니다."""

import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from app.agents.graphs.bookkeeping import BookkeeperState, HumanDecision, build_bookkeeper
from app.contracts.access_errors import InvalidInput, StateConflict
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.jobs.application.runtime import RuntimeAudit
from app.jobs.domain.runtime import RunRead
from app.llm.gateway import LLMGateway
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


class AgentRuntime:
    def __init__(
        self,
        registry: ToolRegistry,
        gateway: LLMGateway,
        audit: RuntimeAudit,
        checkpoints: Callable[[str], AbstractContextManager[BaseCheckpointSaver[Any]]],
    ) -> None:
        self.registry, self.gateway, self.audit, self.checkpoints = (
            registry,
            gateway,
            audit,
            checkpoints,
        )

    def start(self, actor: Principal, company: UUID, transaction: UUID, key: str) -> RunRead:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        context = ToolContext(actor, company)
        self.registry.execute(
            "accounting.get_transaction", {"transaction_id": transaction}, context
        )
        run = self.audit.create(
            actor,
            company,
            transaction,
            self.gateway.provider.code,
            self.gateway.provider.model,
            key,
            digest({"transaction_id": str(transaction), "graph_version": "1"}),
        )
        if run.status in ("WAITING_FOR_INPUT", "COMPLETED", "BLOCKED"):
            return run
        if not self.audit.claim(actor, company, run.id):
            return self.audit.get(actor, company, run.id)
        return self._drive(actor, company, run)

    def resume(
        self,
        actor: Principal,
        company: UUID,
        run_id: UUID,
        expected_version: int,
        decision: HumanDecision,
    ) -> RunRead:
        run = self.audit.get(actor, company, run_id)
        if run.status != "WAITING_FOR_INPUT":
            raise StateConflict()
        if not self.audit.claim(actor, company, run.id, expected_version):
            raise StateConflict()
        return self._drive(actor, company, run, decision)

    def _drive(
        self, actor: Principal, company: UUID, run: RunRead, decision: HumanDecision | None = None
    ) -> RunRead:
        context = ToolContext(actor, company, run.id)
        try:
            with self.checkpoints(run.graph_thread_id) as saver:
                graph = build_bookkeeper(self.registry, self.gateway, context, self.audit, saver)
                config: RunnableConfig = {
                    "configurable": {"thread_id": run.graph_thread_id},
                    "recursion_limit": 20,
                }
                initial: BookkeeperState = {
                    "run_id": str(run.id),
                    "thread_id": run.graph_thread_id,
                    "company_id": str(company),
                    "principal_id": str(actor.user_id),
                    "transaction_id": str(run.transaction_id),
                    "validation_errors": [],
                }
                incoming: Command[Any] | BookkeeperState | None = (
                    Command(resume=decision.model_dump())
                    if decision
                    else (None if saver.get_tuple(config) is not None else initial)
                )
                result = graph.invoke(incoming, config=config)
                waiting = bool(result.get("__interrupt__"))
                verdict = result.get("controller_verdict")
                status = (
                    "WAITING_FOR_INPUT"
                    if waiting
                    else "BLOCKED"
                    if verdict == "BLOCK"
                    else "COMPLETED"
                )
                resource = result.get("result_journal_id")
                self.audit.finish(
                    context,
                    status,
                    "HUMAN_REVIEW" if waiting else "FINALIZING",
                    verdict,
                    UUID(resource) if resource else None,
                    result.get("error_code"),
                )
        except Exception as error:
            # 예외 원문에는 Provider 입력/접속정보가 포함될 수 있어 코드만 기록합니다.
            code = getattr(error, "code", "AGENT_RUNTIME_FAILED")
            self.audit.finish(context, "FAILED", "FAILED", error=code)
        return self.audit.get(actor, company, run.id)
