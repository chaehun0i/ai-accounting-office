"""기존 Closing/Reporting Application을 Registry와 Bookkeeper 질의로 읽습니다."""

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.accounting.journals.application.agent_proposals import AgentProposalService
from app.agents.checkpoints.postgres import PostgresCheckpoints
from app.agents.runtime.service import AgentRuntime
from app.contracts.access_errors import InvalidInput, ResourceNotFound
from app.jobs.application.runtime import RuntimeAudit
from app.jobs.infrastructure.models import ToolExecutionModel
from app.jobs.infrastructure.unit_of_work import RuntimeSQLAlchemyUnitOfWork
from app.llm.gateway import LLMGateway
from app.llm.providers.fake import FakeProvider
from app.tools.accounting import build_registry
from app.tools.contracts import ToolContext
from tests.integration.test_financial_statements import closed_company
from tests.integration.test_journal_flow import prepare


def runtime_for(client, connection, engine):
    services = client.app.state.services
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
        services.closing,
        services.statements,
    )
    registry.record = audit.record_tool
    registry.started = audit.tool_started
    checkpoints = PostgresCheckpoints(
        engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    runtime = AgentRuntime(registry, LLMGateway(FakeProvider()), audit, checkpoints.open)
    client.app.state.services = replace(
        services, tools=registry, runtime_audit=audit, agent_runtime=runtime
    )
    return runtime


def test_closed_statement_query_uses_registry_and_exact_snapshot(
    api_client, auth_service, db_engine
):
    owner, writer, period, _, journal, connection = closed_company(api_client, auth_service)
    generated = api_client.post(
        "/financial-statements/generate",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={"period_id": period},
    )
    assert generated.status_code == 201, generated.text
    runtime = runtime_for(api_client, connection, db_engine)
    actor = api_client.app.state.services.auth.authenticate(
        writer["Authorization"].removeprefix("Bearer ")
    )
    context = ToolContext(actor, UUID(writer["X-Company-ID"]))
    tool = runtime.registry.execute(
        "financial_statement.read",
        {"period_id": period, "statement_type": "INCOME_STATEMENT", "line_code": "NET_PROFIT"},
        context,
    )
    assert tool.model_dump(mode="json")["data"]["sources"][0]["journal_id"] == journal["id"]
    assert tool.model_dump(mode="json")["data"]["lines"][-1]["current_amount"] == "100.0000"
    key = str(uuid4())
    response = api_client.post(
        "/agent/queries/bookkeeper",
        headers={**writer, "Idempotency-Key": key},
        json={"period_id": period, "question": "이번 달 손익이 얼마야?"},
    )
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["status"] == "COMPLETED", answer
    assert Decimal(answer["answer_amount"]) == Decimal("100")
    assert answer["answer_resource_id"] == generated.json()["id"]
    assert answer["answer_source_digest"] == tool.model_dump(mode="json")["data"]["snapshot_digest"]
    assert (
        api_client.post(
            "/agent/queries/bookkeeper",
            headers={**writer, "Idempotency-Key": key},
            json={"period_id": period, "question": "이번 달 손익이 얼마야?"},
        ).json()["id"]
        == answer["id"]
    )
    count = connection.scalar(
        select(func.count())
        .select_from(ToolExecutionModel)
        .where(ToolExecutionModel.agent_run_id == UUID(answer["id"]))
    )
    assert count == 1
    assert api_client.get(f"/agent/runs/{answer['id']}/steps", headers=writer).status_code == 200
    with pytest.raises(InvalidInput):
        runtime.registry.execute(
            "financial_statement.read",
            {"period_id": period, "statement_type": "CASH_FLOW"},
            context,
        )
    with pytest.raises(ResourceNotFound):
        runtime.registry.execute(
            "financial_statement.read",
            {"period_id": period, "statement_type": "BALANCE_SHEET"},
            ToolContext(actor, uuid4()),
        )
    assert (
        api_client.post(
            "/agent/queries/bookkeeper",
            headers={**writer, "Idempotency-Key": str(uuid4())},
            json={"period_id": str(uuid4()), "question": "마감 가능한가?"},
        ).status_code
        == 404
    )


def test_open_period_closing_query_matches_application_check(api_client, auth_service, db_engine):
    _, writer, payload, connection = prepare(api_client, auth_service)
    runtime = runtime_for(api_client, connection, db_engine)
    actor = api_client.app.state.services.auth.authenticate(
        writer["Authorization"].removeprefix("Bearer ")
    )
    company = UUID(writer["X-Company-ID"])
    period = UUID(payload["accounting_period_id"])
    expected = api_client.app.state.services.closing.readiness(actor, company, period)
    response = api_client.post(
        "/agent/queries/bookkeeper",
        headers={**writer, "Idempotency-Key": str(uuid4())},
        json={"period_id": str(period), "question": "이 기간 마감 가능한가?"},
    )
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["status"] == "COMPLETED" and answer["answer_amount"] is None
    assert str(expected.period_status) in answer["answer_text"]
    assert (
        str(sum(check.severity == "BLOCKER" for check in expected.checks)) in answer["answer_text"]
    )
    for check in expected.checks:
        if check.severity == "BLOCKER":
            assert check.check_code in answer["answer_text"]
            assert str(check.amount_impact) in answer["answer_text"]
    tool = runtime.registry.execute(
        "closing.readiness", {"period_id": period}, ToolContext(actor, company)
    )
    assert tool.model_dump(mode="json")["data"]["source_digest"] == expected.source_digest
