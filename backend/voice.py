from __future__ import annotations

import importlib.util
import logging
import os
import pickle
import tempfile
import urllib.request
import uuid
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from backend.config import Settings
from backend.users import get_tts_preferences


# Asr

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
_INITIAL_PROMPT = (
    "Find quotes about courage, wisdom, love, and happiness. "
    "Show me quotes by Einstein, Shakespeare, or Gandhi."
)


class ASRService:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name

    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        import mlx_whisper

        options: dict[str, Any] = {
            "fp16": True,
            "temperature": 0.0,
            "initial_prompt": _INITIAL_PROMPT,
        }
        if language:
            options["language"] = language

        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=self.model_name,
            verbose=False,
            **options,
        )
        text = result["text"].strip()
        logger.info("Transcription completed")
        return {
            "text": text,
            "language": result.get("language", language or "unknown"),
            "backend": "mlx",
            "segments": result.get("segments", []),
        }


# Speaker Id

warnings.filterwarnings(
    "ignore",
    message=".*pkg_resources is deprecated.*",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*__audioread_load.*",
    category=FutureWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*PySoundFile failed.*",
    category=UserWarning,
)


class SpeakerIdentificationService:
    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold
        self._encoder = None

    def _load_encoder(self) -> None:
        if self._encoder is not None:
            return
        try:
            from resemblyzer import VoiceEncoder
        except ImportError:
            logger.error("resemblyzer is not installed")
            raise
        self._encoder = VoiceEncoder(device="cpu")

    @staticmethod
    def _preprocess(audio_path: str) -> np.ndarray:
        import librosa
        from resemblyzer import preprocess_wav

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            waveform, sample_rate = librosa.load(audio_path, sr=None, mono=True)
        return preprocess_wav(
            waveform.astype(np.float32),
            source_sr=sample_rate,
        )

    def extract_embedding(self, audio_path: str) -> np.ndarray:
        self._load_encoder()
        waveform = self._preprocess(audio_path)
        return self._encoder.embed_utterance(waveform)

    def enroll_speaker(
        self,
        audio_files: list[str],
    ) -> np.ndarray:
        if not audio_files:
            raise ValueError("At least 1 audio file required for enrollment")

        self._load_encoder()
        waveforms = []
        for path in audio_files:
            try:
                waveforms.append(self._preprocess(path))
            except Exception as exc:
                logger.warning("Could not process enrollment sample: %s", exc)
        if not waveforms:
            raise ValueError("None of the provided audio files could be processed")
        return self._encoder.embed_speaker(waveforms)

    @staticmethod
    def compute_similarity(first: np.ndarray, second: np.ndarray) -> float:
        if first.shape != second.shape:
            return 0.0
        similarity = float(
            np.dot(
                first / np.linalg.norm(first),
                second / np.linalg.norm(second),
            )
        )
        return float(np.clip(similarity, 0.0, 1.0))

    def identify_speaker(
        self,
        audio_path: str,
        enrolled_users: dict[str, np.ndarray],
    ) -> tuple[str | None, float]:
        if not enrolled_users:
            return None, 0.0

        query = self.extract_embedding(audio_path)
        best_id: str | None = None
        best_score = 0.0
        for user_id, embedding in enrolled_users.items():
            score = self.compute_similarity(query, embedding)
            if score > best_score:
                best_id, best_score = user_id, score
        if best_score < self.threshold:
            return None, best_score
        return best_id, best_score

    @staticmethod
    def save_embedding(embedding: np.ndarray, file_path: str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as file:
            pickle.dump(embedding, file)

    @staticmethod
    def load_embedding(file_path: str) -> np.ndarray:
        with Path(file_path).open("rb") as file:
            return pickle.load(file)

    def load_all_embeddings(self, embeddings_dir: str) -> dict[str, np.ndarray]:
        directory = Path(embeddings_dir)
        if not directory.exists():
            return {}

        users: dict[str, np.ndarray] = {}
        for path in directory.glob("*.pkl"):
            try:
                embedding = self.load_embedding(str(path))
                if embedding.shape != (256,):
                    logger.warning("Skipping incompatible embedding for %s", path.stem)
                    continue
                users[path.stem] = embedding
            except Exception as exc:
                logger.error("Could not load embedding for %s: %s", path.stem, exc)
        return users


# Tts

KOKORO_VOICES = [
    "af_heart",
    "af_bella",
    "af_nicole",
    "af_sarah",
    "af_sky",
    "af_alloy",
    "af_aoede",
    "af_jessica",
    "af_kore",
    "af_nova",
    "af_river",
    "am_adam",
    "am_michael",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_onyx",
    "am_puck",
    "bf_emma",
    "bf_isabella",
    "bf_alice",
    "bf_lily",
    "bm_george",
    "bm_lewis",
    "bm_daniel",
    "bm_fable",
]

DEFAULT_VOICE = "af_heart"
MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/"
    "download/model-files-v1.0/kokoro-v1.0.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/"
    "download/model-files-v1.0/voices-v1.0.bin"
)


class TTSService:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path
        self._kokoro: Any | None = None

    def load_models(self) -> None:
        if self._kokoro is not None:
            return
        from kokoro_onnx import Kokoro

        cache = Path.home() / ".cache" / "kokoro_onnx"
        cache.mkdir(parents=True, exist_ok=True)
        model = cache / "kokoro-v1.0.onnx"
        voices = cache / "voices-v1.0.bin"
        for path, url in ((model, MODEL_URL), (voices, VOICES_URL)):
            if not path.exists():
                logger.info("Downloading Kokoro asset file=%s", path.name)
                urllib.request.urlretrieve(url, path)
        self._kokoro = Kokoro(str(model), str(voices))

    def synthesize_personalized(
        self,
        text: str,
        user_id: str | None = None,
        output_path: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> np.ndarray:
        selected = preferences or self._preferences(user_id)
        voice = str(selected.get("style") or DEFAULT_VOICE)
        if voice not in KOKORO_VOICES:
            voice = DEFAULT_VOICE
        speed = float(selected.get("speaking_rate") or 1.0)
        energy = float(selected.get("energy_scale") or 1.0)

        self.load_models()
        samples, sample_rate = self._kokoro.create(
            text,
            voice=voice,
            speed=speed,
            lang="en-us",
        )
        audio = np.clip(
            np.asarray(samples, dtype=np.float32) * energy,
            -1.0,
            1.0,
        )
        if output_path:
            sf.write(output_path, audio, int(sample_rate))
        logger.info(
            "event=tts voice=%s sample_rate=%d samples=%d",
            voice,
            sample_rate,
            len(audio),
        )
        return audio

    def _preferences(self, user_id: str | None) -> dict[str, Any]:
        defaults = {
            "speaking_rate": 1.0,
            "energy_scale": 1.0,
            "style": DEFAULT_VOICE,
        }
        if not user_id or not self.db_path:
            return defaults
        return {
            **defaults,
            **(get_tts_preferences(user_id, Path(self.db_path)) or {}),
        }


# Voice

class VoiceService:
    """Manage audio transcription, speaker recognition, and synthesis."""

    def __init__(
        self,
        app_settings: Settings,
        speaker_service: SpeakerIdentificationService | None = None,
        asr_service: ASRService | None = None,
        tts_service: TTSService | None = None,
    ):
        self.settings = app_settings
        self.speaker_service = speaker_service or SpeakerIdentificationService(
            threshold=0.75
        )
        self.asr_service = asr_service or ASRService()
        self.tts_service = tts_service or TTSService(
            db_path=str(self.settings.resolved_db_path)
        )
        self.settings.generated_audio_dir.mkdir(parents=True, exist_ok=True)

    def health_flags(self, search_ready: bool) -> dict[str, bool]:
        return {
            "search": search_ready,
            "asr": importlib.util.find_spec("mlx_whisper") is not None,
            "speaker_id": importlib.util.find_spec("resemblyzer") is not None,
            "tts": importlib.util.find_spec("kokoro_onnx") is not None,
            "sqlite": self.settings.resolved_db_path.exists(),
        }

    def transcribe_bytes(self, audio_bytes: bytes, filename: str) -> str:
        temp_path = self.write_temp_file(filename, audio_bytes)
        try:
            result = self.asr_service.transcribe(temp_path)
            return result["text"].strip()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def identify_speaker(self, audio_bytes: bytes, filename: str) -> tuple[str | None, float]:
        temp_path = self.write_temp_file(filename, audio_bytes)
        try:
            enrolled_users = self.speaker_service.load_all_embeddings(str(self.settings.embeddings_dir))
            if not enrolled_users:
                return None, 0.0
            return self.speaker_service.identify_speaker(temp_path, enrolled_users)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def synthesize_audio(
        self,
        text: str,
        user_id: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> tuple[str | None, list[str]]:
        primary_filename = f"{uuid.uuid4().hex}.wav"
        primary_path = self.settings.generated_audio_dir / primary_filename
        try:
            self.tts_service.synthesize_personalized(
                text=text,
                user_id=user_id,
                output_path=str(primary_path),
                preferences=preferences,
            )
            return f"/api/audio/{primary_filename}", []
        except Exception:
            return None, ["tts_unavailable"]

    def resolve_audio_path(self, audio_id: str) -> Path | None:
        candidate = (self.settings.generated_audio_dir / audio_id).resolve()
        try:
            candidate.relative_to(self.settings.generated_audio_dir.resolve())
        except ValueError:
            return None
        return candidate if candidate.exists() else None

    @staticmethod
    def write_temp_file(filename: str, payload: bytes) -> str:
        suffix = Path(filename or "sample.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(payload)
            return temp_file.name
