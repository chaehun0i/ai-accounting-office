"""A model/transport cannot opt into human-confirmed report commands."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.contracts.access_errors import AuthorizationDenied
from app.identity.users.domain.entities import Principal
from app.tools.adapters.langchain import langchain_tools
from app.tools.approved_reports import definition
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


def test_command_requires_server_injected_confirmation_and_is_not_a_model_tool():
    calls = []
    service = SimpleNamespace(request=lambda *args, **kwargs: calls.append(kwargs))
    registry = ToolRegistry(lambda *args: None)
    tool = definition(service)
    registry.register(tool)
    context = ToolContext(Principal(uuid4(), uuid4(), "user@example.com"), uuid4())
    assert langchain_tools(registry, context) == []
    with pytest.raises(AuthorizationDenied):
        registry.execute(tool.tool_code, {"human_confirmed": True}, context)
    assert calls == []
