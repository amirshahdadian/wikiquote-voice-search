"""Application container and lifecycle wiring."""
from __future__ import annotations

from google import genai
from google.genai import types

from backend.app.core.settings import Settings
from backend.app.integrations.audio import SpeakerIdentificationService
from backend.app.integrations.gemini import GeminiService
from backend.app.integrations.neo4j_repository import Neo4jQuoteRepository
from backend.app.services import ConversationService, UserService, VoiceService
from backend.app.services.hybrid_search import HybridSearch
from backend.app.services.query_workflow import build_query_workflow


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
        self.search = HybridSearch(self.repository, gemini_service)
        workflow = build_query_workflow(gemini_service, self.search)

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
