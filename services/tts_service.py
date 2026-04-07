"""
Text-to-Speech (TTS) Service — kokoro-onnx backend
Runs entirely on CPU via ONNX runtime; no CUDA, no NeMo, no MPS complications.

Install:  pip install kokoro-onnx huggingface_hub soundfile
Model:    onnx-community/Kokoro-82M-v1.0-ONNX (~340 MB, downloaded automatically)

Personalization:  each enrolled user is assigned a Kokoro voice preset stored in
the ``style`` column of the ``user_tts_preferences`` SQLite table.  The
``speaking_rate`` column maps directly to Kokoro's ``speed`` parameter.
"""

from __future__ import annotations

import io
import logging
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf

from src.wikiquote_voice.config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kokoro voice presets — 54 voices total; listed here for reference / round-robin
# assignment at enrollment time.
# ---------------------------------------------------------------------------
KOKORO_VOICES: List[str] = [
    # American Female
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "af_alloy", "af_aoede", "af_jessica", "af_kore", "af_nova", "af_river",
    # American Male
    "am_adam", "am_michael", "am_echo", "am_eric", "am_fenrir",
    "am_liam", "am_onyx", "am_puck",
    # British Female
    "bf_emma", "bf_isabella", "bf_alice", "bf_lily",
    # British Male
    "bm_george", "bm_lewis", "bm_daniel", "bm_fable",
]

DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 1.0
SAMPLE_RATE = 24_000          # Kokoro always produces 24 kHz


class TTSService:
    """
    Personalized TTS Service using kokoro-onnx (Kokoro-82M).

    Public interface is identical to the previous NeMo FastPitch+HiFiGAN
    implementation so the orchestrator and backend need no changes.

    Voice personalization:  each user gets a distinct Kokoro voice preset
    (``style`` column in the DB) and a custom speed (``speaking_rate`` column).
    At enrollment time, assign a preset with ``assign_voice_preset()``.
    """

    def __init__(self, device: str = "cpu", db_path: str = None):
        """
        Parameters
        ----------
        device : str
            Kept for API compatibility; kokoro-onnx always runs on CPU via ONNX.
        db_path : str
            Path to the SQLite database that holds ``user_tts_preferences``.
        """
        self.db_path = db_path
        self._kokoro = None
        logger.info(
            "TTSService initialised (backend=kokoro-onnx, db=%s)",
            db_path or "none",
        )

    # ------------------------------------------------------------------
    # Model loading (lazy)
    # ------------------------------------------------------------------
    # GitHub release tag that provides the paired model + voices files
    _MODEL_RELEASE_BASE = (
        "https://github.com/thewh1teagle/kokoro-onnx/releases"
        "/download/model-files-v1.0"
    )
    _MODEL_FILENAME  = "kokoro-v1.0.onnx"   # 310 MB — uses 'tokens' input schema
    _VOICES_FILENAME = "voices-v1.0.bin"     # 27  MB — combined NPZ voices file

    def load_models(self) -> None:
        """Download / load Kokoro model files (called automatically on first use).

        Both files are downloaded from the official kokoro-onnx GitHub releases
        and cached in ~/.cache/kokoro_onnx/ for reuse across runs.
        """
        if self._kokoro is not None:
            return
        try:
            import urllib.request
            from pathlib import Path as _Path
            from kokoro_onnx import Kokoro

            cache_dir = _Path.home() / ".cache" / "kokoro_onnx"
            cache_dir.mkdir(parents=True, exist_ok=True)

            model_path  = cache_dir / self._MODEL_FILENAME
            voices_path = cache_dir / self._VOICES_FILENAME

            for path, filename in [
                (model_path, self._MODEL_FILENAME),
                (voices_path, self._VOICES_FILENAME),
            ]:
                if not path.exists():
                    url = f"{self._MODEL_RELEASE_BASE}/{filename}"
                    logger.info("Downloading %s → %s …", filename, path)
                    urllib.request.urlretrieve(url, path)
                else:
                    logger.info("Using cached %s", path)

            self._kokoro = Kokoro(str(model_path), str(voices_path))
            logger.info("✅ Kokoro-82M loaded (24 kHz, %d voices)", len(KOKORO_VOICES))
        except ImportError:
            logger.error(
                "kokoro-onnx not installed.  Run: pip install kokoro-onnx"
            )
            raise

    # ------------------------------------------------------------------
    # Voice preset helpers
    # ------------------------------------------------------------------
    @staticmethod
    def assign_voice_preset(user_index: int = 0) -> str:
        """
        Return a deterministic Kokoro voice preset for a new user.

        Cycles through ``KOKORO_VOICES`` so each enrolled user gets a
        different audible voice.  Pass the 0-based index of the new user
        in the enrolled-user roster.
        """
        return KOKORO_VOICES[user_index % len(KOKORO_VOICES)]

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Load TTS preferences for a specific user from the SQLite database.

        Returns a dict with at least ``style`` (voice preset) and
        ``speaking_rate`` (speed multiplier).
        """
        if not self.db_path:
            logger.warning("No database path configured; using defaults")
            return self._default_preferences()

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT pitch_scale, speaking_rate, energy_scale, style "
                "FROM user_tts_preferences WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                prefs = {
                    "pitch_scale": float(row[0] or 1.0),
                    "speaking_rate": float(row[1] or DEFAULT_SPEED),
                    "energy_scale": float(row[2] or 1.0),
                    "style": row[3] or DEFAULT_VOICE,
                }
                logger.info("Loaded preferences for '%s': %s", user_id, prefs)
                return prefs

            logger.warning("No preferences for '%s'; using defaults", user_id)
            return self._default_preferences()

        except Exception as exc:
            logger.error("Failed to load preferences for '%s': %s", user_id, exc)
            return self._default_preferences()

    @staticmethod
    def _default_preferences() -> Dict[str, Any]:
        return {
            "pitch_scale": 1.0,
            "speaking_rate": DEFAULT_SPEED,
            "energy_scale": 1.0,
            "style": DEFAULT_VOICE,
        }

    # ------------------------------------------------------------------
    # Core synthesis
    # ------------------------------------------------------------------
    def _synth(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        speed: float = DEFAULT_SPEED,
        lang: str = "en-us",
    ) -> Tuple[np.ndarray, int]:
        """
        Call Kokoro and return ``(samples_float32, sample_rate)``.

        Kokoro always outputs 24 kHz mono float32.
        """
        self.load_models()
        logger.info("Kokoro synthesise — voice=%s  speed=%.2f  text: %s …", voice, speed, text[:60])
        samples, sample_rate = self._kokoro.create(text, voice=voice, speed=speed, lang=lang)
        return np.asarray(samples, dtype=np.float32), int(sample_rate)

    def synthesize(
        self,
        text: str,
        output_path: str = None,
        sample_rate: int = SAMPLE_RATE,
    ) -> np.ndarray:
        """
        Synthesize speech from text with the default voice.

        Parameters
        ----------
        text : str
        output_path : str, optional
            If provided the WAV is written to this path.
        sample_rate : int
            Kept for API compatibility; Kokoro always produces 24 kHz
            regardless of this value.

        Returns
        -------
        np.ndarray — float32 waveform at 24 kHz
        """
        audio, sr = self._synth(text)
        audio = np.clip(audio, -1.0, 1.0)

        if output_path:
            sf.write(output_path, audio, sr)
            logger.info("Audio saved → %s", output_path)

        logger.info("✅ Synthesis complete (%d samples @ %d Hz)", len(audio), sr)
        return audio

    def synthesize_personalized(
        self,
        text: str,
        user_id: str = None,
        output_path: str = None,
        sample_rate: int = SAMPLE_RATE,
        preferences: Dict[str, Any] = None,
    ) -> np.ndarray:
        """
        Synthesize speech with a user's assigned voice preset and speed.

        Parameters
        ----------
        text : str
        user_id : str, optional
            Looks up ``style`` (voice preset) and ``speaking_rate`` from DB.
        output_path : str, optional
        sample_rate : int
            Kept for API compatibility; always outputs 24 kHz.
        preferences : dict, optional
            Overrides DB lookup when supplied directly.

        Returns
        -------
        np.ndarray — float32 waveform at 24 kHz
        """
        if preferences is None:
            preferences = (
                self.get_user_preferences(user_id)
                if user_id
                else self._default_preferences()
            )

        voice = str(preferences.get("style") or DEFAULT_VOICE)
        speed = float(preferences.get("speaking_rate") or DEFAULT_SPEED)
        energy = float(preferences.get("energy_scale") or 1.0)

        # Validate voice; fall back gracefully
        if voice not in KOKORO_VOICES and not voice.startswith(("af_", "am_", "bf_", "bm_")):
            logger.warning("Unknown voice preset '%s'; falling back to %s", voice, DEFAULT_VOICE)
            voice = DEFAULT_VOICE

        logger.info(
            "Personalised synthesis — user=%s  voice=%s  speed=%.2f  energy=%.2f",
            user_id or "(default)", voice, speed, energy,
        )

        try:
            audio, sr = self._synth(text, voice=voice, speed=speed)
            audio = audio * energy
            audio = np.clip(audio, -1.0, 1.0)

            if output_path:
                sf.write(output_path, audio, sr)
                logger.info("Personalised audio saved → %s", output_path)

            logger.info("✅ Personalised synthesis complete")
            return audio

        except Exception as exc:
            logger.error("Personalised synthesis failed: %s — falling back to defaults", exc)
            return self.synthesize(text, output_path=output_path)

    # ------------------------------------------------------------------
    # Bytes-based helpers (for the backend)
    # ------------------------------------------------------------------
    def synthesize_to_bytes(self, text: str, sample_rate: int = SAMPLE_RATE) -> bytes:
        """Synthesize and return raw WAV bytes."""
        audio, sr = self._synth(text)
        audio = np.clip(audio, -1.0, 1.0)
        return self._to_wav_bytes(audio, sr)

    def synthesize_personalized_to_bytes(
        self,
        text: str,
        user_id: str = None,
        sample_rate: int = SAMPLE_RATE,
        preferences: Dict[str, Any] = None,
    ) -> bytes:
        """Synthesize personalized speech and return raw WAV bytes."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp_path = tmp.name
        try:
            self.synthesize_personalized(
                text,
                user_id=user_id,
                output_path=tmp_path,
                preferences=preferences,
            )
            with open(tmp_path, "rb") as fh:
                return fh.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @staticmethod
    def _to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV")
        buf.seek(0)
        return buf.read()

    # ------------------------------------------------------------------
    # Compatibility helper — kept for any callers that probe model state
    # ------------------------------------------------------------------
    def get_backend_info(self) -> Dict[str, Any]:
        return {
            "backend": "kokoro-onnx",
            "model": "Kokoro-82M-v1.0-ONNX",
            "sample_rate": SAMPLE_RATE,
            "voices": KOKORO_VOICES,
            "default_voice": DEFAULT_VOICE,
        }


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------
def main() -> None:
    import sys

    text = (
        "Imagination is more important than knowledge. "
        "Knowledge is limited, but imagination encircles the world."
    )
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])

    svc = TTSService(db_path=str(Path(Config.DATA_DIR) / "wikiquote_voice.db"))
    output = "demo_tts.wav"
    svc.synthesize(text, output_path=output)
    print(f"✅  Saved to: {output}")


if __name__ == "__main__":
    main()
