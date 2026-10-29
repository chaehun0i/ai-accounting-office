"""A previously discovered Tool never grants lasting execution permission."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.contracts.access_errors import AuthorizationDenied
from app.identity.users.domain.entities import Principal
from app.tools.contracts import Empty, Result, ToolContext, ToolDefinition
from app.tools.registry import ToolRegistry


def test_tool_execution_rechecks_revoked_permission() -> None:
    allowed = True
    recorded = []

    def authorize(context: ToolContext, permission: str) -> None:
        if not allowed:
            raise AuthorizationDenied()

    registry = ToolRegistry(authorize, record=lambda *values: recorded.append(values))
    registry.register(
        ToolDefinition(
            "test.read",
            "permission refresh test",
            "account.read",
            Empty,
            Result[Decimal],
            lambda context, payload: Result[Decimal](
                as_of=date(2026, 1, 1), data=Decimal("1.0000")
            ),
        )
    )
    context = ToolContext(Principal(uuid4(), uuid4(), "mcp@example.com"), uuid4())
    assert registry.definitions()[0].tool_code == "test.read"
    assert registry.execute("test.read", {}, context).data == Decimal("1.0000")

    allowed = False
    with pytest.raises(AuthorizationDenied):
        registry.execute("test.read", {}, context)
    assert recorded[-1][-1] == "AUTHORIZATION_DENIED"
