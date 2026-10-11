"""Canonical 정의를 LangChain Tool로 변환하며 실행 정책은 Registry에 남깁니다."""

from typing import Any

from langchain_core.tools import StructuredTool

from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


def langchain_tools(registry: ToolRegistry, context: ToolContext) -> list[StructuredTool]:
    tools = []
    for definition in registry.definitions():

        def execute(_code: str = definition.tool_code, **arguments: Any) -> dict[str, Any]:
            return registry.execute(_code, arguments, context).model_dump(mode="json")

        tools.append(
            StructuredTool.from_function(
                func=execute,
                name=definition.tool_code,
                description=definition.description,
                args_schema=definition.input_schema,
                infer_schema=False,
            )
        )
    return tools
