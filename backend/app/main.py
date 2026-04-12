"""FastAPI entrypoint for the Which Quote web API."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routers.audio import router as audio_router
from backend.app.api.routers.authors import router as authors_router
from backend.app.api.routers.chat import router as chat_router
from backend.app.api.routers.health import router as health_router
from backend.app.api.routers.quotes import router as quotes_router
from backend.app.api.routers.users import router as users_router
from backend.app.api.routers.voice import router as voice_router
from backend.app.container import AppContainer
from backend.app.core.logging import configure_logging
from backend.app.core.settings import settings


def create_app(container: AppContainer | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level)

        if container is not None:
            app.state.container = container
            yield
            return

        app_container = AppContainer(settings)
        app.state.container = app_container
        try:
            yield
        finally:
            app_container.close()

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
    app.include_router(authors_router)
    app.include_router(users_router)
    app.include_router(chat_router)
    app.include_router(voice_router)
    app.include_router(audio_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"name": "Which Quote API", "docs": "/docs"}

    return app


app = create_app()
