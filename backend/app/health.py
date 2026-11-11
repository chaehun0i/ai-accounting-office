from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.core.database.readiness import ReadinessRead

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse, summary="서비스 상태 확인")
def health() -> HealthResponse:
    """서버의 실행 상태만 확인하며, 데이터베이스나 Redis에는 연결하지 않습니다."""
    return HealthResponse()


@router.get("/ready", response_model=ReadinessRead, summary="회계 DB 준비 상태")
def ready(request: Request, response: Response) -> ReadinessRead:
    value: ReadinessRead = request.app.state.database_readiness.inspect()
    response.status_code = 200 if value.status == "ready" else 503
    response.headers["Cache-Control"] = "no-store"
    return value
