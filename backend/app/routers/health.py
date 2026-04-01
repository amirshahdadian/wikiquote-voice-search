"""Health endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_backend_state
from ..schemas import HealthResponse
from ..state import BackendState

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def get_health(state: BackendState = Depends(get_backend_state)) -> HealthResponse:
    return HealthResponse(**state.health_flags())
