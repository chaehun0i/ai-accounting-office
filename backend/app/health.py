from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse, summary="서비스 상태 확인")
def health() -> HealthResponse:
    """서버의 실행 상태만 확인하며, 데이터베이스나 Redis에는 연결하지 않습니다."""
    return HealthResponse()
