"""MCP v2 공식 서버에 같은 Registry를 노출합니다. 원격 공개 서버는 아닙니다."""

from collections.abc import Callable
from dataclasses import replace
from uuid import UUID, uuid5

import anyio
from mcp import types
from mcp.server import Server
from mcp.server.context import ServerRequestContext

from app.contracts.errors import ApplicationError
from app.core.digests import digest
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


def create_mcp_server(registry: ToolRegistry, context: Callable[[], ToolContext]) -> Server[None]:
    async def list_tools(
        ctx: ServerRequestContext[None], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        current = context()
        definitions = []
        for tool in registry.definitions():
            try:
                await anyio.to_thread.run_sync(
                    registry.authorize, current, tool.required_permission
                )
            except ApplicationError:
                continue
            definitions.append(
                types.Tool(
                    name=tool.tool_code,
                    description=tool.description,
                    input_schema=tool.input_schema.model_json_schema(),
                    output_schema=tool.output_schema.model_json_schema(),
                    annotations=types.ToolAnnotations(
                        read_only_hint=tool.tool_class == "READ",
                        destructive_hint=False,
                        open_world_hint=False,
                    ),
                )
            )
        return types.ListToolsResult(tools=definitions)

    async def call_tool(
        ctx: ServerRequestContext[None], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        try:
            current = context()
            # 같은 사용자·회사·명령 입력은 연결을 재생성해도 같은 초안을 재사용합니다.
            invocation = uuid5(
                UUID("137efbac-ae85-4699-b96c-e89e21c9cc10"),
                str(current.principal.user_id)
                + str(current.company_id)
                + params.name
                + digest(params.arguments or {}),
            )
            result = await anyio.to_thread.run_sync(
                registry.execute,
                params.name,
                params.arguments or {},
                replace(current, invocation_id=invocation),
            )
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=result.model_dump_json())],
                structured_content=result.model_dump(mode="json"),
            )
        except ApplicationError as error:
            return types.CallToolResult(
                is_error=True, content=[types.TextContent(type="text", text=error.code)]
            )

    async def resources(
        ctx: ServerRequestContext[None], params: types.PaginatedRequestParams | None
    ) -> types.ListResourcesResult:
        registry.authorize(context(), "account.read")
        return types.ListResourcesResult(
            resources=[
                types.Resource(
                    uri="accounting://company/current/coa",
                    name="현재 회사 활성 분개 계정 검색 (최대 20개)",
                    mime_type="application/json",
                )
            ]
        )

    async def read_resource(
        ctx: ServerRequestContext[None], params: types.ReadResourceRequestParams
    ) -> types.ReadResourceResult:
        if str(params.uri) != "accounting://company/current/coa":
            raise ValueError("지원하지 않는 자료입니다.")
        value = await anyio.to_thread.run_sync(
            registry.execute, "accounting.search_accounts", {}, context()
        )
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=params.uri, mime_type="application/json", text=value.model_dump_json()
                )
            ]
        )

    return Server(
        "ai-accounting-office",
        version=registry.version,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=resources,
        on_read_resource=read_resource,
    )
