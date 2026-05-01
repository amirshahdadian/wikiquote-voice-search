"""Audio-related integrations."""

from .asr import (
    ASRProvider,
    ASRService,
    FasterWhisperProvider,
    MlxWhisperProvider,
    create_asr_provider,
    is_backend_available,
)
from .speaker_id import SpeakerIdentificationService
from .tts import KOKORO_VOICES, TTSService
from .tts_fallback import SimpleTTSService

__all__ = [
    "ASRProvider",
    "ASRService",
    "FasterWhisperProvider",
    "KOKORO_VOICES",
    "MlxWhisperProvider",
    "SimpleTTSService",
    "SpeakerIdentificationService",
    "TTSService",
    "create_asr_provider",
    "is_backend_available",
]
