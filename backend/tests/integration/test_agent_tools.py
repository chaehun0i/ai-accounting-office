from uuid import UUID, uuid4

import anyio
import pytest

from app.contracts.access_errors import InvalidInput, ResourceNotFound
from app.core.database.framework_schema import assert_framework_schema
from app.core.database.schema import assert_relational_schema
from app.tools.adapters.langchain import langchain_tools
from app.tools.adapters.mcp import create_mcp_server
from app.tools.contracts import ToolContext
from tests.integration.test_agent_runtime import agent_environment as agent_environment
from tests.integration.test_agent_runtime import start


def test_real_application_tools(api_client, agent_environment):
    owner, writer, source, runtime, checkpoints, connection = agent_environment
    actor = api_client.app.state.services.auth.authenticate(
        writer["Authorization"].removeprefix("Bearer ")
    )
    context = ToolContext(actor, UUID(writer["X-Company-ID"]))
    account = api_client.get("/accounts", headers=writer).json()[0]
    period = api_client.get("/accounting/periods", headers=writer).json()[0]
    calls = {
        "accounting.search_accounts": {},
        "accounting.get_transaction": {"transaction_id": source["id"]},
        "evidence.get_transaction_evidence": {"transaction_id": source["id"]},
        "accounting.get_ledger": {
            "account_id": account["id"],
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        },
        "accounting.get_trial_balance": {"period_id": period["id"]},
        "finance.list_receivables": {"as_of": "2026-01-31"},
        "finance.list_payables": {"as_of": "2026-01-31"},
        "finance.get_ar_reconciliation": {"as_of": "2026-01-31"},
        "finance.get_ap_reconciliation": {"as_of": "2026-01-31"},
    }
    adapted = {tool.name: tool for tool in langchain_tools(runtime.registry, context)}
    for name, arguments in calls.items():
        value = runtime.registry.execute(name, arguments, context)
        assert value.model_dump()["status"] == "SUCCEEDED"
        assert adapted[name].invoke(arguments)["status"] == "SUCCEEDED"
    with pytest.raises(InvalidInput):
        runtime.registry.execute("accounting.search_accounts", {"sql": "SELECT 1"}, context)
    with pytest.raises(ResourceNotFound):
        runtime.registry.execute(
            "accounting.get_transaction", {"transaction_id": str(uuid4())}, context
        )
    run = start(api_client, writer, source)
    with checkpoints.open(run["graph_thread_id"]):
        pass
    assert_relational_schema(connection)
    assert_framework_schema(connection, require_installed=True)


def test_mcp_protocol_same_registry(api_client, agent_environment):
    from mcp.client import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    owner, writer, source, runtime, checkpoints, connection = agent_environment
    actor = api_client.app.state.services.auth.authenticate(
        writer["Authorization"].removeprefix("Bearer ")
    )
    context = ToolContext(actor, UUID(writer["X-Company-ID"]))
    server = create_mcp_server(runtime.registry, lambda: context)

    async def exercise():
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            async with anyio.create_task_group() as group:
                group.start_soon(
                    server.run, *server_streams, server.create_initialization_options()
                )
                async with ClientSession(*client_streams) as client:
                    await client.initialize()
                    listed = await client.list_tools()
                    expected = {tool.tool_code: tool for tool in runtime.registry.definitions()}
                    assert {tool.name for tool in listed.tools} == set(expected)
                    for tool in listed.tools:
                        assert (
                            tool.input_schema
                            == expected[tool.name].input_schema.model_json_schema()
                        )
                    result = await client.call_tool(
                        "accounting.get_transaction", {"transaction_id": source["id"]}
                    )
                    assert not result.is_error
                    assert result.structured_content["data"]["amount"] == source["amount"]
                    denied = await client.call_tool("journal.post", {})
                    assert denied.is_error
                group.cancel_scope.cancel()

    anyio.run(exercise)
