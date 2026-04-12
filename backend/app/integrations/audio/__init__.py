"""Audio-related integrations."""

from .asr import ASRService
from .speaker_id import SpeakerIdentificationService
from .tts import KOKORO_VOICES, TTSService
from .tts_fallback import SimpleTTSService

__all__ = [
    "ASRService",
    "KOKORO_VOICES",
    "SimpleTTSService",
    "SpeakerIdentificationService",
    "TTSService",
]

