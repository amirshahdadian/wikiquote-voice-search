"""
Speaker Identification Service — resemblyzer backend
Runs entirely on CPU; no CUDA, no NeMo, no MPS complications.

Install:  pip install resemblyzer
Model:    GE2E speaker encoder (downloaded automatically on first use, ~17 MB)

Embedding: 256-dim float32 L2-normalised vector per speaker.
Cosine similarity is used for enrol/identify (both vectors are unit vectors,
so dot-product == cosine similarity).
"""

from __future__ import annotations

import logging
import os
import pickle
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from backend.app.core.settings import settings

# ── Silence noisy third-party import warnings ─────────────────────────────
# webrtcvad (a resemblyzer dependency) still uses pkg_resources which is
# scheduled for removal in Setuptools 81+.
warnings.filterwarnings(
    "ignore",
    message=".*pkg_resources is deprecated.*",
    category=UserWarning,
)
# librosa ≥ 0.10 deprecates the audioread fallback; suppress the
# FutureWarning so it does not pollute server logs during WebM loading.
warnings.filterwarnings(
    "ignore",
    message=".*__audioread_load.*",
    category=FutureWarning,
)
# Also silence soundfile's "PySoundFile failed" user-warning that fires
# for browser-recorded WebM/Opus files.
warnings.filterwarnings(
    "ignore",
    message=".*PySoundFile failed.*",
    category=UserWarning,
)

logger = logging.getLogger(__name__)


class SpeakerIdentificationService:
    """
    Speaker Identification using resemblyzer (GE2E speaker encoder).

    Public interface is kept stable for the canonical backend voice service.

    Enrollment:    record N clips → compute embeddings → average → store .pkl
    Identification: embed query clip → cosine-sim against enrolled set → best match
    """

    def __init__(self, threshold: float = 0.75, device: str = "cpu"):
        """
        Parameters
        ----------
        threshold : float
            Cosine-similarity threshold for positive identification (0–1).
            0.75 works well for short ~5 s clips; lower to 0.70 if you see
            false rejections, raise toward 0.80 to reduce false accepts.
        device : str
            Kept for API compatibility; resemblyzer always runs on CPU.
        """
        self.threshold = threshold
        self._encoder = None
        logger.info(
            "SpeakerIdentificationService initialised (threshold=%.2f, backend=resemblyzer)",
            threshold,
        )

    # ------------------------------------------------------------------
    # Model loading (lazy)
    # ------------------------------------------------------------------
    def _load_encoder(self):
        if self._encoder is not None:
            return
        try:
            from resemblyzer import VoiceEncoder
            self._encoder = VoiceEncoder(device="cpu")
            logger.info("✅ resemblyzer VoiceEncoder loaded")
        except ImportError:
            logger.error("resemblyzer is not installed.  Run: pip install resemblyzer")
            raise

    # ------------------------------------------------------------------
    # Audio preprocessing helper
    # ------------------------------------------------------------------
    @staticmethod
    def _preprocess(audio_path: str) -> np.ndarray:
        """
        Load any audio file and return a resemblyzer-ready float32 waveform.

        The browser records audio as WebM/Opus which soundfile cannot read.
        We use librosa (which handles any format via its ffmpeg/audioread chain)
        to decode first, then hand the numpy array to resemblyzer's
        ``preprocess_wav`` for VAD trimming and normalisation.

        All third-party warnings from this decode path are suppressed at
        module level above.
        """
        import librosa
        from resemblyzer import preprocess_wav

        # Load at native sample rate, mono.  librosa handles WebM, Opus,
        # MP4, WAV, MP3, FLAC — anything the browser might produce.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wav_arr, sr = librosa.load(audio_path, sr=None, mono=True)

        # preprocess_wav accepts a numpy array + source_sr; it resamples
        # to 16 kHz and applies WebRTC VAD internally.
        return preprocess_wav(wav_arr.astype(np.float32), source_sr=sr)

    # ------------------------------------------------------------------
    # Core: extract embedding
    # ------------------------------------------------------------------
    def extract_embedding(self, audio_path: str) -> np.ndarray:
        """
        Compute a 256-dim L2-normalised speaker embedding for one audio clip.

        Parameters
        ----------
        audio_path : str
            Path to any audio file (WAV, MP3, FLAC, …).

        Returns
        -------
        np.ndarray, shape (256,), dtype float32
        """
        self._load_encoder()
        logger.info("Extracting embedding from: %s", audio_path)
        wav = self._preprocess(audio_path)
        embedding = self._encoder.embed_utterance(wav)   # (256,) float32, unit vector
        logger.info("Embedding extracted — shape %s", embedding.shape)
        return embedding

    # ------------------------------------------------------------------
    # Enrollment
    # ------------------------------------------------------------------
    def enroll_speaker(self, user_id: str, audio_files: List[str]) -> np.ndarray:
        """
        Enroll a user by averaging embeddings from multiple clips.

        Parameters
        ----------
        user_id : str
        audio_files : list[str]
            At least 1 path; 3–5 clips recommended for robustness.

        Returns
        -------
        np.ndarray — averaged, L2-normalised embedding, shape (256,)
        """
        if not audio_files:
            raise ValueError("At least 1 audio file required for enrollment")

        self._load_encoder()
        logger.info("Enrolling '%s' with %d clip(s)", user_id, len(audio_files))

        wavs = []
        for path in audio_files:
            try:
                wavs.append(self._preprocess(path))
            except Exception as exc:
                logger.warning("Skipping %s: %s", path, exc)

        if not wavs:
            raise ValueError("None of the provided audio files could be processed")

        # embed_speaker averages all clips then re-normalises — ideal for enrollment
        embedding = self._encoder.embed_speaker(wavs)   # (256,) unit vector
        logger.info(
            "✅ '%s' enrolled — %d/%d clips used, embedding shape %s",
            user_id, len(wavs), len(audio_files), embedding.shape,
        )
        return embedding

    # ------------------------------------------------------------------
    # Similarity
    # ------------------------------------------------------------------
    @staticmethod
    def compute_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Cosine similarity between two embeddings.

        Because resemblyzer returns L2-normalised vectors the dot product
        equals cosine similarity exactly.  We clip to [0, 1] to avoid
        tiny numerical negatives.

        Returns 0.0 if the embeddings have different dimensions (stale
        embedding saved by a previous backend with a different vector size).
        """
        if emb1.shape != emb2.shape:
            return 0.0
        sim = float(np.dot(emb1 / np.linalg.norm(emb1), emb2 / np.linalg.norm(emb2)))
        return float(np.clip(sim, 0.0, 1.0))

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------
    def identify_speaker(
        self,
        audio_path: str,
        enrolled_users: Dict[str, np.ndarray],
    ) -> Tuple[Optional[str], float]:
        """
        Identify the speaker in an audio clip.

        Parameters
        ----------
        audio_path : str
        enrolled_users : dict[str, np.ndarray]
            {user_id: embedding}

        Returns
        -------
        (user_id, confidence) or (None, best_score) if below threshold
        """
        if not enrolled_users:
            logger.warning("No enrolled users — cannot identify")
            return None, 0.0

        query = self.extract_embedding(audio_path)
        best_id, best_score = None, 0.0

        for uid, enrolled_emb in enrolled_users.items():
            score = self.compute_similarity(query, enrolled_emb)
            logger.debug("  %s → %.4f", uid, score)
            if score > best_score:
                best_score = score
                best_id = uid

        if best_score >= self.threshold:
            logger.info("✅ Identified: %s (%.2f%%)", best_id, best_score * 100)
            return best_id, best_score

        logger.info("❌ Unknown speaker — best=%s (%.2f%%)", best_id, best_score * 100)
        return None, best_score

    def verify_speaker(
        self,
        audio_path: str,
        user_id: str,
        enrolled_users: Dict[str, np.ndarray],
    ) -> Tuple[bool, float]:
        """Verify whether an audio clip belongs to a specific enrolled user."""
        if user_id not in enrolled_users:
            logger.warning("User '%s' not enrolled", user_id)
            return False, 0.0
        query = self.extract_embedding(audio_path)
        score = self.compute_similarity(query, enrolled_users[user_id])
        match = score >= self.threshold
        logger.info(
            "Verification %s — %s (%.2f%%)",
            user_id, "✅ MATCH" if match else "❌ NO MATCH", score * 100,
        )
        return match, score

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_embedding(self, embedding: np.ndarray, file_path: str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(embedding, fh)
        logger.info("Embedding saved → %s", path)

    def load_embedding(self, file_path: str) -> np.ndarray:
        with open(file_path, "rb") as fh:
            return pickle.load(fh)

    def load_all_embeddings(self, embeddings_dir: str) -> Dict[str, np.ndarray]:
        """Load every *.pkl file in a directory as {stem: embedding}.

        Embeddings saved by a previous backend (e.g. NeMo TitaNet = 192-dim)
        are incompatible with resemblyzer (256-dim).  They are skipped with a
        clear message so identification degrades gracefully rather than crashing.
        """
        _EXPECTED_DIM = 256
        directory = Path(embeddings_dir)
        users: Dict[str, np.ndarray] = {}
        if not directory.exists():
            logger.warning("Embeddings directory not found: %s", directory)
            return users
        for pkl in directory.glob("*.pkl"):
            try:
                emb = self.load_embedding(pkl)
                if emb.shape != (_EXPECTED_DIM,):
                    logger.warning(
                        "Skipping stale embedding for '%s' — shape %s is "
                        "incompatible with resemblyzer (%d-dim).  "
                        "Please re-enroll this user.",
                        pkl.stem, emb.shape, _EXPECTED_DIM,
                    )
                    continue
                users[pkl.stem] = emb
                logger.info("Loaded embedding for '%s' (shape %s)", pkl.stem, emb.shape)
            except Exception as exc:
                logger.error("Failed to load '%s': %s", pkl.stem, exc)
        logger.info("Loaded %d valid enrolled user(s)", len(users))
        return users


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python speaker_identification.py enroll <user_id> <audio1.wav> [...]")
        print("  python speaker_identification.py identify <audio.wav>")
        print("  python speaker_identification.py verify <user_id> <audio.wav>")
        return

    svc = SpeakerIdentificationService(threshold=0.75)
    embeddings_dir = settings.embeddings_dir
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    cmd = sys.argv[1].lower()

    if cmd == "enroll" and len(sys.argv) >= 4:
        user_id = sys.argv[2]
        audio_files = sys.argv[3:]
        emb = svc.enroll_speaker(user_id, audio_files)
        svc.save_embedding(emb, embeddings_dir / f"{user_id}.pkl")
        print(f"✅ '{user_id}' enrolled — embedding saved to {embeddings_dir}")

    elif cmd == "identify" and len(sys.argv) >= 3:
        enrolled = svc.load_all_embeddings(str(embeddings_dir))
        uid, conf = svc.identify_speaker(sys.argv[2], enrolled)
        if uid:
            print(f"✅ Identified: {uid}  ({conf:.0%})")
        else:
            print(f"❌ Unknown speaker (best score: {conf:.0%})")

    elif cmd == "verify" and len(sys.argv) >= 4:
        enrolled = svc.load_all_embeddings(str(embeddings_dir))
        match, conf = svc.verify_speaker(sys.argv[3], sys.argv[2], enrolled)
        print(f"{'✅ MATCH' if match else '❌ NO MATCH'} — {conf:.0%}")

    else:
        print(f"Unknown command or missing arguments: {sys.argv[1]}")


if __name__ == "__main__":
    main()
