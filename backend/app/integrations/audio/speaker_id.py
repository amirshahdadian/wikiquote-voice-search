"""Local speaker enrollment and identification with resemblyzer."""
from __future__ import annotations

import logging
import pickle
import warnings
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

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
    def __init__(self, threshold: float = 0.75, device: str = "cpu"):
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
        user_id: str,
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
