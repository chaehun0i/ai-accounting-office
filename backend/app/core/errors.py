import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException


class FieldError(BaseModel):
    field: str
    code: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    field_errors: list[FieldError] = Field(default_factory=list)


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    body = ErrorResponse(code=code, message=message, request_id=request_id)
    return JSONResponse(
        status_code=status, content=body.model_dump(), headers={"X-Request-ID": request_id}
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = "RESOURCE_NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        message = (
            "요청하신 내용을 찾을 수 없습니다."
            if exc.status_code == 404
            else "요청을 처리할 수 없습니다. 입력 내용과 요청 경로를 확인해 주세요."
        )
        return error_response(request, exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            request, 422, "INVALID_INPUT", "입력한 내용을 확인한 후 다시 시도해 주세요."
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        return internal_error_response(request)


def internal_error_response(request: Request) -> JSONResponse:
    logging.getLogger("accounting_office").error(
        "요청 처리 중 예기치 않은 오류가 발생했습니다. 요청 ID=%s",
        getattr(request.state, "request_id", "unknown"),
    )
    return error_response(
        request, 500, "INTERNAL_ERROR", "처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."
    )
