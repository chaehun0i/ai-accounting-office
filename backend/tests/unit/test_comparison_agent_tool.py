"""비교 Tool은 권한과 Application 판정을 그대로 보존합니다."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.contracts.access_errors import AuthorizationDenied, InvalidInput
from app.identity.users.domain.entities import Principal
from app.tools.comparatives import definition
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


@pytest.mark.parametrize("status,reasons", [("READY", []), ("BLOCKED", ["SOURCE_NOT_COMPARABLE"])])
def test_comparison_readiness_preserves_service_verdict(status, reasons):
    company, current, prior = uuid4(), uuid4(), uuid4()
    context = ToolContext(Principal(uuid4(), uuid4(), "review@example.com"), company)
    calls = []

    def readiness(actor, scope, period, comparison):
        calls.append((actor, scope, period, comparison))
        return dict(
            status=status,
            reasons=reasons,
            source_digest="a" * 64 if status == "READY" else None,
            supported_statements=["BALANCE_SHEET", "INCOME_STATEMENT"],
            unsupported_statements=["CASH_FLOW", "CHANGES_IN_EQUITY", "NOTES"],
        )

    permissions = []
    registry = ToolRegistry(lambda ctx, permission: permissions.append((ctx, permission)))
    registry.register(definition(SimpleNamespace(readiness=readiness)))
    tool = registry.definitions()[0]
    assert tool.tool_class == "READ" and tool.side_effect_level == "NONE"
    result = registry.execute(
        tool.tool_code, dict(period_id=str(current), comparison_period_id=str(prior)), context
    )
    assert result.data.status == status
    assert result.data.reasons == reasons
    assert calls == [(context.principal, company, current, prior)]
    assert permissions == [(context, "financial_statement.read")]
    with pytest.raises(InvalidInput):
        registry.execute(
            tool.tool_code,
            dict(period_id=str(current), comparison_period_id=str(prior), company_id=str(uuid4())),
            context,
        )
    assert len(calls) == 1


def test_denied_comparison_never_reaches_service():
    def denied(context, permission):
        raise AuthorizationDenied()

    registry = ToolRegistry(denied)
    registry.register(
        definition(SimpleNamespace(readiness=lambda *args: pytest.fail("service invoked")))
    )
    with pytest.raises(AuthorizationDenied):
        registry.execute(
            "financial_statement.comparison_readiness",
            {},
            ToolContext(Principal(uuid4(), uuid4(), "review@example.com"), uuid4()),
        )
