from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from google import genai
from google.genai import types

from backend.config import Settings, configure_logging, settings
from backend.gemini import GeminiService
from backend.models import (
    ChatQueryRequest,
    ChatQueryResponse,
    HealthResponse,
    QuoteHit,
    TTSPreviewRequest,
    TTSPreviewResponse,
    UserPreferences,
    UserProfile,
    VoiceQueryResponse,
)
from backend.neo4j import Neo4jQuoteRepository
from backend.search import ConversationService, HybridSearch, QueryWorkflow
from backend.users import UserService
from backend.voice import SpeakerIdentificationService, VoiceService


# Container

class AppContainer:
    """Own the process-wide clients and application services."""

    def __init__(self, app_settings: Settings):
        self.settings = app_settings
        self.settings.generated_audio_dir.mkdir(parents=True, exist_ok=True)
        self.settings.embeddings_dir.mkdir(parents=True, exist_ok=True)

        self.gemini_client = self._gemini_client(app_settings)
        gemini_service = GeminiService(
            self.gemini_client,
            app_settings.gemini_llm_model,
            app_settings.gemini_embedding_model,
            app_settings.gemini_embedding_dimensions,
        )
        self.repository = Neo4jQuoteRepository(
            app_settings.neo4j_uri,
            app_settings.neo4j_username,
            app_settings.neo4j_password,
        )
        self.search = HybridSearch(
            self.repository,
            gemini_service,
            semantic_ready=self.repository.embeddings_ready(
                app_settings.gemini_embedding_model,
                app_settings.gemini_embedding_dimensions,
            ),
        )
        workflow = QueryWorkflow(gemini_service, self.search)

        speaker_service = SpeakerIdentificationService(threshold=0.75)
        self.voice = VoiceService(app_settings, speaker_service=speaker_service)
        self.users = UserService(app_settings, speaker_service=speaker_service)
        self.conversation = ConversationService(workflow, self.users, self.voice)

    @staticmethod
    def _gemini_client(app_settings: Settings):
        if app_settings.gemini_api_key is None:
            return None
        return genai.Client(
            api_key=app_settings.gemini_api_key.get_secret_value(),
            http_options=types.HttpOptions(
                timeout=int(app_settings.gemini_timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(
                    attempts=app_settings.gemini_max_retries
                ),
            ),
        )

    def health_flags(self) -> dict[str, bool]:
        ready = self.repository.is_ready()
        return self.voice.health_flags(search_ready=ready)

    def close(self) -> None:
        self.repository.close()
        if self.gemini_client is not None:
            self.gemini_client.close()


# Dependencies

def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_search_service(container: AppContainer = Depends(get_container)) -> HybridSearch:
    return container.search


def get_user_service(container: AppContainer = Depends(get_container)) -> UserService:
    return container.users


def get_voice_service(container: AppContainer = Depends(get_container)) -> VoiceService:
    return container.voice


def get_conversation_service(container: AppContainer = Depends(get_container)) -> ConversationService:
    return container.conversation


# Health

health_router = APIRouter(prefix="/api/health", tags=["health"])


@health_router.get("", response_model=HealthResponse)
def get_health(container: AppContainer = Depends(get_container)) -> HealthResponse:
    return HealthResponse(**container.health_flags())


# Quotes

quotes_router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@quotes_router.get("/search", response_model=list[QuoteHit])
async def search_quotes(
    query: str = Query(min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
    search_service: HybridSearch = Depends(get_search_service),
) -> list[QuoteHit]:
    return await search_service.search_text(query, limit=limit)


@quotes_router.get("/autocomplete", response_model=list[QuoteHit])
def autocomplete(
    query: str = Query(min_length=1, description="Partial quote fragment for live suggestions"),
    limit: int = Query(default=5, ge=1, le=10),
    search_service: HybridSearch = Depends(get_search_service),
) -> list[QuoteHit]:
    return search_service.autocomplete(query, limit=limit)


# Users

users_router = APIRouter(prefix="/api/users", tags=["users"])


@users_router.get("", response_model=list[UserProfile])
def list_users(user_service: UserService = Depends(get_user_service)) -> list[UserProfile]:
    return [UserProfile(**user) for user in user_service.list_users()]


@users_router.get("/{user_id}", response_model=UserProfile)
def get_user(user_id: str, user_service: UserService = Depends(get_user_service)) -> UserProfile:
    user = user_service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfile(**user)


@users_router.post("/register", response_model=UserProfile)
async def register_user(
    display_name: str = Form(...),
    group_identifier: str | None = Form(default=None),
    speaking_rate: float = Form(default=1.0),
    energy_scale: float = Form(default=1.0),
    audio_samples: list[UploadFile] = File(...),
    user_service: UserService = Depends(get_user_service),
) -> UserProfile:
    if len(audio_samples) < 3:
        raise HTTPException(status_code=400, detail="At least 3 audio samples are required")

    preferences = UserPreferences(
        speaking_rate=speaking_rate,
        energy_scale=energy_scale,
    ).model_dump()
    uploads = [(sample.filename or "sample.wav", await sample.read()) for sample in audio_samples]

    try:
        user = user_service.register_user(display_name, group_identifier, preferences, uploads)
        return UserProfile(**user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@users_router.post("/{user_id}/re-enroll", response_model=UserProfile)
async def re_enroll_user(
    user_id: str,
    audio_samples: list[UploadFile] = File(...),
    user_service: UserService = Depends(get_user_service),
) -> UserProfile:
    if len(audio_samples) < 3:
        raise HTTPException(status_code=400, detail="At least 3 audio samples are required")

    uploads = [(sample.filename or "sample.wav", await sample.read()) for sample in audio_samples]
    try:
        user = user_service.re_enroll_user(user_id, uploads)
        return UserProfile(**user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@users_router.delete("/{user_id}", status_code=204, response_class=Response)
def delete_user(user_id: str, user_service: UserService = Depends(get_user_service)) -> Response:
    try:
        user_service.delete_user(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


# Chat

chat_router = APIRouter(prefix="/api/chat", tags=["chat"])


@chat_router.post("/query", response_model=ChatQueryResponse)
async def chat_query(
    request: ChatQueryRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ChatQueryResponse:
    payload = await conversation_service.process_chat_query(
        message=request.message,
        conversation_id=request.conversation_id,
        selected_user_id=request.selected_user_id,
    )
    return ChatQueryResponse(**payload)


# Voice

voice_router = APIRouter(prefix="/api", tags=["voice"])


@voice_router.post("/voice/query", response_model=VoiceQueryResponse)
async def voice_query(
    audio: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    selected_user_id: str | None = Form(default=None),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> VoiceQueryResponse:
    payload = await conversation_service.process_voice_query(
        audio_bytes=await audio.read(),
        filename=audio.filename or "voice.wav",
        conversation_id=conversation_id,
        selected_user_id=selected_user_id,
    )
    return VoiceQueryResponse(**payload)


@voice_router.post("/tts/preview", response_model=TTSPreviewResponse)
def tts_preview(
    request: TTSPreviewRequest,
    voice_service: VoiceService = Depends(get_voice_service),
) -> TTSPreviewResponse:
    audio_url, warnings = voice_service.synthesize_audio(
        text=request.text,
        user_id=request.user_id,
        preferences=request.preferences.model_dump() if request.preferences else None,
    )
    return TTSPreviewResponse(audio_url=audio_url, warnings=warnings)


# Audio

audio_router = APIRouter(prefix="/api/audio", tags=["audio"])


@audio_router.get("/{audio_id}")
def get_generated_audio(
    audio_id: str,
    voice_service: VoiceService = Depends(get_voice_service),
) -> FileResponse:
    audio_path = voice_service.resolve_audio_path(audio_id)
    if audio_path is None:
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path=audio_path, filename=audio_path.name)


# Main

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
    app.include_router(users_router)
    app.include_router(chat_router)
    app.include_router(voice_router)
    app.include_router(audio_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"name": "Which Quote API", "docs": "/docs"}

    return app


app = create_app()
