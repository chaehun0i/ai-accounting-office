from ipaddress import ip_address, ip_network
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request

from app.composition import Services
from app.contracts.access_errors import AuthenticationRequired, AuthorizationDenied
from app.contracts.errors import DatabaseUnavailable
from app.core.security import digest
from app.identity.auth.application.service import AuthService
from app.identity.sessions.domain.entities import RequestFacts
from app.identity.users.domain.entities import Principal


def services(request: Request) -> Services:
    value: Services = request.app.state.services
    return value


def auth_service(container: Annotated[Services, Depends(services)]) -> AuthService:
    if container.auth is None:
        raise DatabaseUnavailable()
    return container.auth


def principal(
    auth: Annotated[AuthService, Depends(auth_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if authorization is None:
        raise AuthenticationRequired()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationRequired()
    return auth.authenticate(token)


def csrf(request: Request) -> None:
    # 커스텀 헤더와 정확한 Origin 검증으로 cookie 기반 요청의 CSRF를 차단합니다.
    origin = request.headers.get("origin")
    if request.headers.get("x-csrf-protection") != "1" or (
        origin and origin != request.app.state.frontend_origin
    ):
        raise AuthorizationDenied()


def facts(request: Request) -> RequestFacts:
    host = request.client.host if request.client else "unknown"
    try:
        address = ip_address(host)
        prefix = str(ip_network(f"{address}/{24 if address.version == 4 else 56}", strict=False))
    except ValueError:
        prefix = "unknown"
    # 프록시 헤더는 신뢰하지 않습니다. 운영 프록시는 신뢰할 hop을 별도로 설정해야 합니다.
    agent = request.headers.get("user-agent")
    return RequestFacts(UUID(request.state.request_id), prefix, digest(agent) if agent else None)
