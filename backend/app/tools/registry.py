"""모든 Adapter가 동일한 검증·권한·허용목록을 통과합니다."""

from collections.abc import Callable
from time import monotonic

from pydantic import BaseModel, ValidationError

from app.contracts.access_errors import AuthorizationDenied, InvalidInput
from app.core.digests import digest
from app.tools.contracts import ToolContext, ToolDefinition

FORBIDDEN = frozenset(
    {
        "journal.post",
        "period.close",
        "period.reopen",
        "payment.execute",
        "tax.filing.submit",
        "tax.rule.activate",
        "arbitrary_db_query",
    }
)


class ToolRegistry:
    version = "1"

    def __init__(
        self,
        authorize: Callable[[ToolContext, str], None],
        record: Callable[[ToolContext, str, str, str, str, int, str | None], None] | None = None,
        started: Callable[[ToolContext, str], None] | None = None,
    ) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self.authorize = authorize
        self.record = record
        self.started = started

    def register(self, definition: ToolDefinition) -> None:
        if definition.tool_code in self._tools or definition.tool_code in FORBIDDEN:
            raise ValueError("중복되거나 금지된 도구입니다.")
        if definition.tool_class not in {"READ", "PROPOSE"}:
            raise ValueError("이 런타임은 조회와 제안 도구만 허용합니다.")
        self._tools[definition.tool_code] = definition

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._tools.values())

    def execute(self, code: str, arguments: dict[str, object], context: ToolContext) -> BaseModel:
        definition = self._tools.get(code)
        if definition is None:
            raise AuthorizationDenied()
        start = monotonic()
        input_digest = "0" * 64
        output_digest = ""
        status, error_code = "FAILED", None
        try:
            if self.started:
                self.started(context, code)
            self.authorize(context, definition.required_permission)
            try:
                payload = definition.input_schema.model_validate(arguments)
            except ValidationError:
                raise InvalidInput() from None
            input_digest = digest(payload.model_dump(mode="json"))
            result = definition.handler(context, payload)
            result = definition.output_schema.model_validate(result.model_dump())
            if monotonic() - start > definition.timeout_seconds:
                raise TimeoutError()
            output_digest = digest(result.model_dump(mode="json"))
            status = "SUCCEEDED"
            return result
        except Exception as error:
            error_code = getattr(error, "code", "TOOL_FAILED")
            raise
        finally:
            if self.record:
                self.record(
                    context,
                    code,
                    input_digest,
                    output_digest,
                    status,
                    int((monotonic() - start) * 1000),
                    error_code,
                )
