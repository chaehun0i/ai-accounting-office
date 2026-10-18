"""실제 PostgreSQL 체크포인트와 API, Application Tool을 끝까지 실행합니다."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import sessionmaker

from app.accounting.journals.application.agent_proposals import AgentProposalService
from app.agents.checkpoints.postgres import PostgresCheckpoints
from app.agents.runtime.service import AgentRuntime
from app.companies.infrastructure.models import MembershipModel
from app.jobs.application.runtime import RuntimeAudit
from app.jobs.infrastructure.models import ToolExecutionModel
from app.jobs.infrastructure.unit_of_work import RuntimeSQLAlchemyUnitOfWork
from app.llm.gateway import LLMGateway
from app.llm.providers.fake import FakeProvider
from app.tools.accounting import build_registry
from tests.integration.test_journal_flow import prepare


@pytest.fixture
def agent_environment(api_client, auth_service, db_engine):
    owner, writer, payload, connection = prepare(api_client, auth_service)
    services = api_client.app.state.services
    factory = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        autobegin=False,
        join_transaction_mode="create_savepoint",
    )
    audit = RuntimeAudit(lambda: RuntimeSQLAlchemyUnitOfWork(factory))
    registry = build_registry(
        services.accounting,
        services.transactions,
        services.accounting_reports,
        services.finance,
        services.finance_reports,
        AgentProposalService(services.journals, services.journal_commands),
    )
    registry.record = audit.record_tool
    registry.started = audit.tool_started
    checkpoints = PostgresCheckpoints(
        db_engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    runtime = AgentRuntime(registry, LLMGateway(FakeProvider()), audit, checkpoints.open)
    api_client.app.state.services = replace(
        services, tools=registry, agent_runtime=runtime, runtime_audit=audit
    )
    response = api_client.post(
        "/transactions",
        headers=writer,
        json={
            "transaction_date": "2026-01-02",
            "accounting_date": "2026-01-02",
            "description": "회계 제안 검증",
            "amount": "100.0000",
            "direction": "INFLOW",
            "source_id": str(uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return owner, writer, response.json(), runtime, checkpoints, connection


def start(client, writer, transaction, key=None):
    response = client.post(
        "/agent/runs/bookkeeper",
        headers={**writer, "Idempotency-Key": key or str(uuid4())},
        json={"transaction_id": transaction["id"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_postgres_interrupt_reconstructed_resume(api_client, agent_environment):
    owner, writer, source, runtime, checkpoints, connection = agent_environment
    key = str(uuid4())
    run = start(api_client, writer, source, key)
    assert run["status"] == "WAITING_FOR_INPUT", run
    assert run["controller_verdict"] == "REVIEW"
    assert run["pending_action"] == "REVIEW_PROPOSAL"
    assert start(api_client, writer, source, key)["id"] == run["id"]
    with checkpoints.open(run["graph_thread_id"]) as saver:
        assert saver.get_tuple({"configurable": {"thread_id": run["graph_thread_id"]}})
    import os
    import subprocess
    import sys

    # 별도 Python 프로세스에서도 같은 PostgreSQL 체크포인트를 읽을 수 있습니다.
    env = {**os.environ, "VERIFY_AGENT_THREAD": run["graph_thread_id"]}
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; from sqlalchemy.engine import make_url; "
            "from app.agents.checkpoints.postgres import PostgresCheckpoints; "
            "c=PostgresCheckpoints(make_url(os.environ['TEST_POSTGRES_URL'])"
            ".set(drivername='postgresql').render_as_string(hide_password=False)); "
            "thread=os.environ['VERIFY_AGENT_THREAD'];\n"
            "with c.open(thread) as saver: "
            "assert saver.get_tuple({'configurable': {'thread_id': thread}}) is not None",
        ],
        env=env,
        check=True,
        timeout=30,
    )
    assert (
        connection.scalar(
            text("SELECT count(*) FROM journal_entries WHERE source_transaction_id=:transaction"),
            {"transaction": UUID(source["id"])},
        )
        == 0
    )
    steps = api_client.get(f"/agent/runs/{run['id']}/steps", headers=writer)
    assert steps.status_code == 200 and len(steps.json()) >= 8
    # Gateway/Graph/checkpointer 객체를 모두 재구성해도 기존 thread를 재개합니다.
    replacement = AgentRuntime(
        runtime.registry,
        LLMGateway(FakeProvider()),
        runtime.audit,
        PostgresCheckpoints(checkpoints._connection_string).open,
    )
    api_client.app.state.services = replace(
        api_client.app.state.services, agent_runtime=replacement
    )
    response = api_client.post(
        f"/agent/runs/{run['id']}/resume",
        headers=writer,
        json={"expected_version": run["version"], "decision": "CONTINUE"},
    )
    assert response.status_code == 200, response.text
    final = response.json()
    assert final["status"] == "COMPLETED", final
    journal = api_client.get("/journals/" + final["result_journal_id"], headers=writer).json()
    assert journal["status"] == "DRAFT"
    assert journal["approved_at"] is None and journal["posted_at"] is None
    assert journal["total_debit"] == journal["total_credit"] == source["amount"]
    count = connection.scalar(
        select(func.count())
        .select_from(ToolExecutionModel)
        .where(ToolExecutionModel.agent_run_id == UUID(run["id"]))
    )
    assert count == 6
    events = api_client.get(f"/agent/runs/{run['id']}/events", headers=writer).json()
    assert events[-1]["event_type"] == "COMPLETED"
    assert "TOOL_STARTED" in {e["event_type"] for e in events}
    assert len({e["event_seq"] for e in events}) == len(events)
    response = api_client.get(
        f"/agent/runs/{run['id']}/stream",
        headers=writer,
        params={"after_seq": events[-2]["event_seq"]},
    )
    assert response.status_code == 200 and "COMPLETED" in response.text


def test_wrong_company_permission_and_invalid_input(api_client, agent_environment):
    owner, writer, source, runtime, checkpoints, connection = agent_environment
    forged = {**writer, "X-Company-ID": str(uuid4()), "Idempotency-Key": str(uuid4())}
    assert (
        api_client.post(
            "/agent/runs/bookkeeper", headers=forged, json={"transaction_id": source["id"]}
        ).status_code
        == 404
    )
    unauthenticated = {k: v for k, v in writer.items() if k != "Authorization"}
    assert api_client.get("/agent/runs/" + str(uuid4()), headers=unauthenticated).status_code == 401
    assert (
        api_client.post(
            "/agent/runs/bookkeeper",
            headers={**writer, "Idempotency-Key": "extra"},
            json={"transaction_id": source["id"], "company_id": owner["X-Company-ID"]},
        ).status_code
        == 422
    )
    owner_actor = api_client.app.state.services.auth.authenticate(
        owner["Authorization"].removeprefix("Bearer ")
    )
    connection.execute(
        update(MembershipModel)
        .where(
            MembershipModel.company_id == UUID(owner["X-Company-ID"]),
            MembershipModel.user_id == owner_actor.user_id,
        )
        .values(role_code="VIEWER")
    )
    assert (
        api_client.post(
            "/agent/runs/bookkeeper",
            headers={**owner, "Idempotency-Key": "owner"},
            json={"transaction_id": source["id"]},
        ).status_code
        == 403
    )
    assert (
        api_client.post(
            "/agent/runs/bookkeeper",
            headers={**writer, "Idempotency-Key": "missing"},
            json={"transaction_id": str(uuid4())},
        ).status_code
        == 404
    )


def test_closed_period_controller_blocks(api_client, agent_environment):
    owner, writer, source, runtime, checkpoints, connection = agent_environment
    connection.execute(
        text("UPDATE accounting_periods SET status='CLOSED' WHERE company_id=:company"),
        {"company": UUID(writer["X-Company-ID"])},
    )
    run = start(api_client, writer, source)
    assert run["status"] == "BLOCKED", run
    assert run["error_code"] == "PERIOD_NOT_OPEN"
    assert run["result_journal_id"] is None


@pytest.mark.parametrize("attack", ["account", "evidence", "amount", "same_account"])
def test_provider_hallucination_is_blocked(api_client, agent_environment, attack):
    from app.llm.contracts import AccountSelection

    owner, writer, source, runtime, checkpoints, connection = agent_environment

    class InvalidProvider(FakeProvider):
        def generate(self, task, facts, schema, timeout_seconds):
            value = super().generate(task, facts, schema, timeout_seconds)
            if task == "select_accounts":
                data = value.model_dump()
                if attack == "account":
                    data["debit_account_id"] = uuid4()
                elif attack == "evidence":
                    data["evidence_ids"] = [uuid4()]
                elif attack == "same_account":
                    data["credit_account_id"] = data["debit_account_id"]
                else:
                    # 검증되지 않은 Provider가 Pydantic 생성까지 우회한 경우도 차단합니다.
                    class ExtraAmount(AccountSelection):
                        amount: str = "999999"

                    return ExtraAmount.model_validate(data)
                return schema.model_validate(data)
            return value

    runtime.gateway = LLMGateway(InvalidProvider())
    run = start(api_client, writer, source)
    assert run["status"] == "BLOCKED", run
    assert run["result_journal_id"] is None


def test_stale_resume_and_rejection(api_client, agent_environment):
    owner, writer, source, runtime, checkpoints, connection = agent_environment
    run = start(api_client, writer, source)
    url = f"/agent/runs/{run['id']}/resume"
    stale = api_client.post(
        url, headers=writer, json={"expected_version": run["version"] - 1, "decision": "CONTINUE"}
    )
    assert stale.status_code == 409
    rejected = api_client.post(
        url, headers=writer, json={"expected_version": run["version"], "decision": "REJECT"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "COMPLETED"
    assert rejected.json()["result_journal_id"] is None


def test_source_change_during_interrupt_fails_safe(api_client, agent_environment):
    from app.contracts.access_errors import VersionConflict

    owner, writer, source, runtime, checkpoints, connection = agent_environment
    run = start(api_client, writer, source)
    connection.execute(
        text("UPDATE transactions SET version=version+1 WHERE id=:id"), {"id": UUID(source["id"])}
    )
    response = api_client.post(
        f"/agent/runs/{run['id']}/resume",
        headers=writer,
        json={"expected_version": run["version"], "decision": "CONTINUE"},
    )
    assert response.json()["status"] == "FAILED", response.text
    assert response.json()["error_code"] == "VERSION_CONFLICT"
    assert response.json()["result_journal_id"] is None
    services = api_client.app.state.services
    actor = services.auth.authenticate(writer["Authorization"].removeprefix("Bearer "))
    proposals = AgentProposalService(services.journals, services.journal_commands)
    accounts = api_client.get("/accounts", headers=writer).json()
    accounts = [a for a in accounts if a["posting_allowed"] and a["status"] == "ACTIVE"]
    candidate = proposals.candidate(
        actor,
        UUID(writer["X-Company-ID"]),
        UUID(source["id"]),
        2,
        UUID(accounts[0]["id"]),
        UUID(accounts[1]["id"]),
        (),
    )
    # 검증과 실제 초안 저장 사이의 변경도 Accounting Command의 source lock 안에서 차단합니다.
    connection.execute(
        text("UPDATE transactions SET version=version+1 WHERE id=:id"), {"id": UUID(source["id"])}
    )
    with pytest.raises(VersionConflict):
        proposals.handoff(actor, candidate, uuid4(), 2)
    assert (
        connection.scalar(
            text("SELECT count(*) FROM journal_entries WHERE source_transaction_id=:transaction"),
            {"transaction": UUID(source["id"])},
        )
        == 0
    )


def test_runtime_audit_append_only_and_checkpoint_allowlist(api_client, agent_environment):
    from sqlalchemy.exc import DBAPIError

    from app.core.database.framework_schema import assert_framework_schema
    from app.core.database.schema import SchemaPolicyError

    owner, writer, source, runtime, checkpoints, connection = agent_environment
    start(api_client, writer, source)
    for table in ("tool_executions", "job_events"):
        with pytest.raises(DBAPIError), connection.begin_nested():
            connection.execute(
                text(f"DELETE FROM {table} WHERE company_id=:company"),
                {"company": UUID(writer["X-Company-ID"])},
            )
    with connection.begin_nested() as savepoint:
        connection.execute(text("CREATE TABLE agent_checkpoints.forbidden (payload JSONB)"))
        with pytest.raises(SchemaPolicyError):
            assert_framework_schema(connection, require_installed=True)
        savepoint.rollback()
    assert_framework_schema(connection, require_installed=True)
