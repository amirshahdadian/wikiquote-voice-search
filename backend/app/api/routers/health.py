"""Health endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_container
from backend.app.api.schemas import HealthResponse
from backend.app.container import AppContainer

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def get_health(container: AppContainer = Depends(get_container)) -> HealthResponse:
    return HealthResponse(**container.health_flags())
