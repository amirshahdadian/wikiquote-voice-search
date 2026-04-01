"""FastAPI dependencies for shared backend state."""
from __future__ import annotations

from fastapi import Request

from .state import BackendState


def get_backend_state(request: Request) -> BackendState:
    return request.app.state.backend
