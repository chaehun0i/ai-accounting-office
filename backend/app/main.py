from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.accounting.api.router import router as accounting_router
from app.accounting.journals.api.router import router as journal_router
from app.accounting.transactions.api.router import router as transaction_router
from app.companies.api.router import router as companies_router
from app.composition import create_services
from app.core.config import Settings, load_settings
from app.core.errors import internal_error_response, register_error_handlers
from app.core.logging import configure_logging
from app.health import router as health_router
from app.identity.auth.api.router import router as auth_router
from app.identity.invitations.api.router import router as invitations_router
from app.intake.api.router import router as intake_router
from app.onboarding.api.router import router as onboarding_router


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message["headers"].append((b"x-request-id", request_id.encode()))
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            # ASGI 서버가 민감정보를 포함할 수 있는 예외 원문을 로그에 남기지 않도록 합니다.
            if response_started:
                raise RuntimeError("응답 전송이 중단되었습니다.") from None
            response = internal_error_response(Request(scope))
            await response(scope, receive, send_with_id)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else load_settings()
    configure_logging()
    engine, container = create_services(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="AI Accounting Office", version="0.1.0", debug=False, lifespan=lifespan)
    app.state.services = container
    app.state.frontend_origin = str(settings.frontend_origin).rstrip("/")
    app.state.secure_cookies = settings.app_environment in ("staging", "production")
    app.state.refresh_cookie_name = (
        "__Host-aao-refresh" if app.state.secure_cookies else "aao-refresh"
    )
    app.state.refresh_seconds = settings.refresh_token_ttl_seconds
    app.state.environment = settings.app_environment
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.frontend_origin).rstrip("/")],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-CSRF-Protection",
            "X-Company-ID",
            "Idempotency-Key",
        ],
        allow_credentials=True,
    )
    app.include_router(onboarding_router)
    app.include_router(intake_router)
    app.include_router(accounting_router)
    app.include_router(transaction_router)
    app.include_router(journal_router)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(companies_router)
    app.include_router(invitations_router)
    register_error_handlers(app)
    return app
