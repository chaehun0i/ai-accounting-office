from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.contracts.access_errors import AuthenticationRequired
from app.identity.auth.api.dependencies import auth_service, csrf, facts, principal
from app.identity.auth.api.schemas import (
    AuthRead,
    CommandResult,
    LoginCommand,
    RegisterCommand,
    UserRead,
)
from app.identity.auth.application.service import AuthResult, AuthService
from app.identity.users.domain.entities import Principal

router = APIRouter(prefix="/auth", tags=["인증"])
Auth = Annotated[AuthService, Depends(auth_service)]
Actor = Annotated[Principal, Depends(principal)]


def auth_response(result: AuthResult, request: Request, response: Response) -> AuthRead:
    response.set_cookie(
        request.app.state.refresh_cookie_name,
        result.refresh_token,
        max_age=request.app.state.refresh_seconds,
        httponly=True,
        secure=request.app.state.secure_cookies,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return AuthRead(
        user=UserRead.from_user(result.user),
        access_token=result.access_token,
        expires_in=result.expires_in,
    )


@router.post("/register", response_model=AuthRead, status_code=201, dependencies=[Depends(csrf)])
def register(
    payload: RegisterCommand, request: Request, response: Response, auth: Auth
) -> AuthRead:
    result = auth.register(str(payload.email), payload.password.get_secret_value(), facts(request))
    return auth_response(result, request, response)


@router.post("/login", response_model=AuthRead, dependencies=[Depends(csrf)])
def login(payload: LoginCommand, request: Request, response: Response, auth: Auth) -> AuthRead:
    result = auth.login(str(payload.email), payload.password.get_secret_value(), facts(request))
    return auth_response(result, request, response)


@router.post("/refresh", response_model=AuthRead, dependencies=[Depends(csrf)])
def refresh(request: Request, response: Response, auth: Auth) -> AuthRead:
    token = request.cookies.get(request.app.state.refresh_cookie_name)
    if not token:
        raise AuthenticationRequired()
    return auth_response(auth.refresh(token, facts(request)), request, response)


@router.get("/me", response_model=UserRead)
def me(actor: Actor, auth: Auth, response: Response) -> UserRead:
    response.headers["Cache-Control"] = "no-store"
    return UserRead.from_user(auth.me(actor))


def logout_response(request: Request, response: Response) -> CommandResult:
    response.delete_cookie(
        request.app.state.refresh_cookie_name,
        path="/",
        secure=request.app.state.secure_cookies,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return CommandResult()


@router.post("/logout", response_model=CommandResult, dependencies=[Depends(csrf)])
def logout(request: Request, response: Response, actor: Actor, auth: Auth) -> CommandResult:
    auth.logout(actor, facts(request))
    return logout_response(request, response)


@router.post("/logout-all", response_model=CommandResult, dependencies=[Depends(csrf)])
def logout_all(request: Request, response: Response, actor: Actor, auth: Auth) -> CommandResult:
    auth.logout(actor, facts(request), all_sessions=True)
    return logout_response(request, response)
