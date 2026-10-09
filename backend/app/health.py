from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse, summary="Process liveness")
def health() -> HealthResponse:
    """Liveness only; no database or Redis connection is attempted."""
    return HealthResponse()
