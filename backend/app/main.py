"""FastAPI entrypoint for the Which Quote web API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.audio import router as audio_router
from .routers.chat import router as chat_router
from .routers.health import router as health_router
from .routers.quotes import router as quotes_router
from .routers.users import router as users_router
from .routers.voice import router as voice_router
from .settings import settings
from .state import BackendState


def create_app(backend_state: Optional[BackendState] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if backend_state is not None:
            app.state.backend = backend_state
            yield
            return

        state = BackendState(settings)
        app.state.backend = state
        try:
            yield
        finally:
            state.close()

    app = FastAPI(
        title="Which Quote API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(quotes_router)
    app.include_router(users_router)
    app.include_router(chat_router)
    app.include_router(voice_router)
    app.include_router(audio_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"name": "Which Quote API", "docs": "/docs"}

    return app


app = create_app()
