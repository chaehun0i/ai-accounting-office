"""현재 사용자 토큰과 회사 컨텍스트로만 실행하는 로컬 MCP 진입점입니다."""

import os
from uuid import UUID

import anyio
from mcp.server.stdio import stdio_server

from app.composition import create_services
from app.core.config import load_settings
from app.tools.adapters.mcp import create_mcp_server
from app.tools.contracts import ToolContext


async def serve() -> None:
    engine, services = create_services(load_settings())
    try:
        if services.auth is None or services.tools is None:
            raise RuntimeError("인증 설정을 확인해 주세요.")
        auth, registry = services.auth, services.tools
        company = UUID(os.environ["MCP_COMPANY_ID"])
        token = os.environ["MCP_ACCESS_TOKEN"]

        def context() -> ToolContext:
            return ToolContext(auth.authenticate(token), company)

        server = create_mcp_server(registry, context)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        engine.dispose()


if __name__ == "__main__":
    anyio.run(serve)
