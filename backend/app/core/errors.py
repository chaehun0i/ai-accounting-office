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
        return error_response(request, exc.status_code, code, "Request could not be completed")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "INVALID_INPUT", "Request validation failed")

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("accounting_office").error(
            "Unhandled request failure request_id=%s",
            getattr(request.state, "request_id", "unknown"),
        )
        return error_response(request, 500, "INTERNAL_ERROR", "Internal server error")
