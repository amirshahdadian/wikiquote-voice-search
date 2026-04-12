"""Application container and lifecycle wiring."""
from __future__ import annotations

from backend.app.core.settings import Settings
from backend.app.integrations.audio import SpeakerIdentificationService
from backend.app.services import ConversationService, QuoteSearchService, UserService, VoiceService


class AppContainer:
    """Own all backend runtime services and shared resources."""

    def __init__(self, app_settings: Settings):
        self.settings = app_settings
        self.settings.generated_audio_dir.mkdir(parents=True, exist_ok=True)
        self.settings.embeddings_dir.mkdir(parents=True, exist_ok=True)

        speaker_service = SpeakerIdentificationService(threshold=0.75)
        self.quote_search = QuoteSearchService(app_settings)
        self.voice = VoiceService(app_settings, speaker_service=speaker_service)
        self.users = UserService(app_settings, speaker_service=speaker_service)
        self.conversation = ConversationService(
            self.quote_search,
            self.users,
            self.voice,
            app_settings.conversation_history_limit,
        )

    def health_flags(self) -> dict[str, bool]:
        return self.voice.health_flags(search_ready=self.quote_search.repository.driver is not None)

    def close(self) -> None:
        self.quote_search.close()

