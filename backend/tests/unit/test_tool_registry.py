"""Registry 밖 실행과 context 위조를 차단합니다."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.contracts.access_errors import AuthorizationDenied, InvalidInput, ResourceNotFound
from app.identity.users.domain.entities import Principal
from app.tools.adapters.langchain import langchain_tools
from app.tools.contracts import Empty, Result, ToolContext, ToolDefinition
from app.tools.registry import FORBIDDEN, ToolFailure, ToolRegistry


def context():
    return ToolContext(Principal(uuid4(), uuid4(), "test@example.com"), uuid4())


def definition():
    return ToolDefinition(
        "test.read",
        "검증용 조회",
        "account.read",
        Empty,
        Result[Decimal],
        lambda c, p: Result[Decimal](as_of=date(2026, 1, 1), data=Decimal("123456789.1234")),
    )


def test_duplicate_forbidden_and_unauthorized():
    registry = ToolRegistry(lambda c, p: None)
    registry.register(definition())
    with pytest.raises(ValueError):
        registry.register(definition())
    with pytest.raises(AuthorizationDenied):
        registry.execute("journal.post", {}, context())
    assert not FORBIDDEN.intersection(t.tool_code for t in registry.definitions())


def test_context_injection_and_precision():
    registry = ToolRegistry(lambda c, p: None)
    registry.register(definition())
    with pytest.raises(InvalidInput):
        registry.execute("test.read", {"company_id": str(uuid4())}, context())
    value = registry.execute("test.read", {}, context())
    assert value.model_dump(mode="json")["data"] == "123456789.1234"


def test_permission_and_langchain_schema():
    def deny(c, p):
        raise AuthorizationDenied()

    registry = ToolRegistry(deny)
    registry.register(definition())
    adapted = langchain_tools(registry, context())[0]
    assert adapted.args_schema is definition().input_schema
    assert adapted.description == definition().description
    with pytest.raises(AuthorizationDenied):
        adapted.invoke({})
    audit = []

    def hidden(c, p):
        raise ResourceNotFound()

    registry.authorize = hidden
    registry.record = lambda *values: audit.append(values)
    with pytest.raises(ResourceNotFound):
        registry.execute("test.read", {}, context())
    assert audit[-1][-1] == "AUTHORIZATION_DENIED"


def test_output_validation():
    from dataclasses import replace

    registry = ToolRegistry(lambda c, p: None)

    class WrongOutput(BaseModel):
        unrelated: str = "값"

    registry.register(replace(definition(), handler=lambda c, p: WrongOutput()))
    with pytest.raises(ToolFailure):
        registry.execute("test.read", {}, context())
