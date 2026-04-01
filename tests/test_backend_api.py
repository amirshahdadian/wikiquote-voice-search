"""FastAPI API tests using a lightweight fake backend state."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class FakeSearchService:
    def search_quotes(self, query: str, limit: int = 5) -> list[dict]:
        results = [
            {
                "quote_text": "To be, or not to be: that is the question.",
                "author_name": "William Shakespeare",
                "source_title": "Hamlet",
                "relevance_score": 0.98,
                "search_type": "partial_quote",
            },
            {
                "quote_text": "Brevity is the soul of wit.",
                "author_name": "William Shakespeare",
                "source_title": "Hamlet",
                "relevance_score": 0.76,
                "search_type": "topic_search",
            },
        ]
        return results[:limit]

    def get_random_quote(self) -> dict:
        return {
            "quote_text": "Knowledge is power.",
            "author_name": "Francis Bacon",
            "source_title": "Meditationes Sacrae",
            "relevance_score": 0.81,
            "search_type": "random",
        }


class FakeBackendState:
    def __init__(self, audio_dir: Path):
        self.audio_dir = audio_dir
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.search_service = FakeSearchService()
        self.users = {
            "amir": {
                "user_id": "amir",
                "display_name": "Amir",
                "group_identifier": "nlp-a",
                "has_embedding": True,
                "preferences": {
                    "pitch_scale": 1.0,
                    "speaking_rate": 1.0,
                    "energy_scale": 1.0,
                    "style": "neutral",
                },
            }
        }
        self.audio_file = self.audio_dir / "preview.wav"
        self.audio_file.write_bytes(b"RIFFstub")
        self.re_enroll_calls = 0

    def close(self) -> None:
        return None

    def health_flags(self) -> dict[str, bool]:
        return {
            "search": True,
            "asr": True,
            "speaker_id": True,
            "tts": True,
            "sqlite": True,
        }

    def list_users(self) -> list[dict]:
        return sorted(self.users.values(), key=lambda item: item["display_name"].lower())

    def get_user(self, user_id: str) -> dict | None:
        return self.users.get(user_id)

    def register_user(
        self,
        display_name: str,
        group_identifier: str | None,
        preferences: dict,
        audio_samples: list[tuple[str, bytes]],
    ) -> dict:
        user_id = display_name.lower().replace(" ", "-")
        user = {
            "user_id": user_id,
            "display_name": display_name,
            "group_identifier": group_identifier,
            "has_embedding": len(audio_samples) >= 3,
            "preferences": {**preferences, "style": preferences.get("style", "neutral")},
        }
        self.users[user_id] = user
        return user

    def update_user_preferences(self, user_id: str, preferences: dict) -> dict:
        user = self.users[user_id]
        user["preferences"] = {**preferences, "style": preferences.get("style", "neutral")}
        return user

    def re_enroll_user(
        self,
        user_id: str,
        audio_samples: list[tuple[str, bytes]],
    ) -> dict:
        self.re_enroll_calls += 1
        user = self.users[user_id]
        user["has_embedding"] = len(audio_samples) >= 3
        return user

    def delete_user(self, user_id: str) -> None:
        self.users.pop(user_id)

    def process_chat_query(
        self,
        message: str,
        conversation_id: str | None = None,
        selected_user_id: str | None = None,
    ) -> dict:
        if "nothing" in message.lower():
            return {
                "conversation_id": conversation_id or "conv-empty",
                "recognized_user": None,
                "intent_type": "topic_search",
                "response_text": "I could not find an exact match for 'nothing'. Please try again or rephrase.",
                "best_quote": None,
                "related_quotes": [],
                "audio_url": None,
                "warnings": ["no_quote_found"],
            }

        return {
            "conversation_id": conversation_id or "conv-123",
            "recognized_user": (
                {
                    "user_id": selected_user_id,
                    "display_name": self.users[selected_user_id]["display_name"],
                    "confidence": 1.0,
                    "source": "selected",
                }
                if selected_user_id
                else None
            ),
            "intent_type": "quote_lookup",
            "response_text": 'The best matching quote is "Knowledge is power." by Francis Bacon from Meditationes Sacrae.',
            "best_quote": self.search_service.get_random_quote(),
            "related_quotes": self.search_service.search_quotes(message, limit=3)[1:],
            "audio_url": "/api/audio/preview.wav",
            "warnings": ["multiple_close_matches"],
        }

    def process_voice_query(
        self,
        audio_bytes: bytes,
        filename: str,
        conversation_id: str | None = None,
        selected_user_id: str | None = None,
    ) -> dict:
        recognized_user = None
        warnings = []
        if selected_user_id:
            recognized_user = {
                "user_id": selected_user_id,
                "display_name": self.users[selected_user_id]["display_name"],
                "confidence": 1.0,
                "source": "selected",
            }
        else:
            warnings.append("speaker_not_recognized")

        return {
            "conversation_id": conversation_id or "voice-123",
            "transcript": "Who said knowledge is power?",
            "normalized_transcript": "who said knowledge is power",
            "recognized_user": recognized_user,
            "intent_type": "quote_lookup",
            "response_text": 'The best matching quote is "Knowledge is power." by Francis Bacon from Meditationes Sacrae.',
            "best_quote": self.search_service.get_random_quote(),
            "related_quotes": self.search_service.search_quotes("knowledge", limit=3)[1:],
            "audio_url": "/api/audio/preview.wav",
            "warnings": warnings,
        }

    def create_tts_preview(
        self,
        text: str,
        user_id: str | None = None,
        preferences: dict | None = None,
    ) -> dict:
        return {"audio_url": "/api/audio/preview.wav", "warnings": []}

    def resolve_audio_path(self, audio_id: str) -> Path | None:
        if audio_id == "preview.wav":
            return self.audio_file
        return None


class BackendApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fake_state = FakeBackendState(Path(self.temp_dir.name))
        self.client_context = TestClient(create_app(backend_state=self.fake_state))
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def _audio_files(self, count: int) -> list[tuple[str, bytes, str]]:
        return [
            ("audio_samples", (f"sample-{idx}.wav", b"fake-audio", "audio/wav"))
            for idx in range(count)
        ]

    def test_health_returns_service_flags(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "search": True,
                "asr": True,
                "speaker_id": True,
                "tts": True,
                "sqlite": True,
            },
        )

    def test_quotes_search_returns_ranked_results(self) -> None:
        response = self.client.get("/api/quotes/search", params={"query": "to be", "limit": 2})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["author_name"], "William Shakespeare")

    def test_register_requires_three_audio_samples(self) -> None:
        response = self.client.post(
            "/api/users/register",
            data={"display_name": "Mina"},
            files=self._audio_files(2),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("At least 3 audio samples", response.json()["detail"])

    def test_register_accepts_valid_samples(self) -> None:
        response = self.client.post(
            "/api/users/register",
            data={
                "display_name": "Mina",
                "group_identifier": "nlp-b",
                "pitch_scale": "1.2",
                "speaking_rate": "0.9",
                "energy_scale": "1.1",
            },
            files=self._audio_files(3),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user_id"], "mina")
        self.assertTrue(payload["has_embedding"])
        self.assertEqual(payload["preferences"]["pitch_scale"], 1.2)

    def test_update_preferences_updates_user_record(self) -> None:
        response = self.client.put(
            "/api/users/amir/preferences",
            json={"pitch_scale": 1.3, "speaking_rate": 0.8, "energy_scale": 1.1, "style": "neutral"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["preferences"]["pitch_scale"], 1.3)
        self.assertEqual(payload["preferences"]["speaking_rate"], 0.8)

    def test_reenroll_replaces_embedding(self) -> None:
        response = self.client.post(
            "/api/users/amir/re-enroll",
            files=self._audio_files(3),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["has_embedding"])
        self.assertEqual(self.fake_state.re_enroll_calls, 1)

    def test_delete_user_removes_profile(self) -> None:
        response = self.client.delete("/api/users/amir")
        self.assertEqual(response.status_code, 204)
        self.assertNotIn("amir", self.fake_state.users)

    def test_text_query_returns_warning_shape(self) -> None:
        response = self.client.post(
            "/api/chat/query",
            json={"message": "nothing here", "conversation_id": "conv-a"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["warnings"], ["no_quote_found"])
        self.assertIsNone(payload["best_quote"])

    def test_voice_query_returns_transcript_and_audio_url(self) -> None:
        response = self.client.post(
            "/api/voice/query",
            data={"conversation_id": "voice-a"},
            files={"audio": ("voice.wav", b"fake-audio", "audio/wav")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["conversation_id"], "voice-a")
        self.assertEqual(payload["transcript"], "Who said knowledge is power?")
        self.assertEqual(payload["audio_url"], "/api/audio/preview.wav")
        self.assertIn("speaker_not_recognized", payload["warnings"])

    def test_audio_endpoint_serves_generated_file(self) -> None:
        response = self.client.get("/api/audio/preview.wav")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"RIFFstub")


if __name__ == "__main__":
    unittest.main()
