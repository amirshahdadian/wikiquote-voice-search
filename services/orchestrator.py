"""
Voice Pipeline Orchestrator
Coordinates the complete voice interaction flow:
Record → Speaker ID → ASR → Chatbot → Personalized TTS → Response
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import tempfile
import sounddevice as sd
import soundfile as sf
import numpy as np

# Import services
from services.speaker_identification import SpeakerIdentificationService
from services.asr_service import ASRService
from services.chatbot_service import ChatbotService
from services.tts_service import TTSService
from src.wikiquote_voice.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VoiceOrchestrator:
    """
    Orchestrates complete voice interaction pipeline.
    Handles multi-user voice queries with personalized responses.
    """

    def __init__(self, sample_rate: int = 16000, threshold: float = 0.75):
        """
        Initialize voice orchestrator.

        Parameters
        ----------
        sample_rate : int
            Audio sample rate for microphone recording.
        threshold : float
            Cosine-similarity threshold for speaker identification.
        """
        self.sample_rate = sample_rate
        self.threshold = threshold

        logger.info("Initializing Voice Orchestrator…")

        # Speaker identification (resemblyzer, CPU)
        self.speaker_id = SpeakerIdentificationService(threshold=threshold)
        logger.info("✅ Speaker ID initialized (backend=resemblyzer)")

        # ASR (mlx-whisper, Apple Silicon GPU)
        self.asr = ASRService()
        logger.info("✅ ASR initialized (backend=mlx-whisper)")

        # Chatbot / dialogue
        self.chatbot = ChatbotService()
        logger.info("✅ Chatbot initialized")

        # TTS (kokoro-onnx, CPU)
        db_path = Path(Config.DATA_DIR) / "wikiquote_voice.db"
        self.tts = TTSService(db_path=str(db_path))
        logger.info("✅ TTS initialized (backend=kokoro-onnx)")

        # Pre-load enrolled speaker embeddings
        embeddings_dir = Path(Config.DATA_DIR) / "embeddings"
        self.enrolled_users = self.speaker_id.load_all_embeddings(str(embeddings_dir))
        logger.info("✅ Loaded %d enrolled user(s)", len(self.enrolled_users))

        logger.info("🎉 Voice Orchestrator ready!")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def record_audio(self, duration: int = 5) -> str:
        """
        Record audio from the default microphone.

        Returns the path to a temporary WAV file.
        """
        logger.info("🎤 Recording for %d seconds…", duration)
        print(f"🎤 Speak now! Recording for {duration} seconds…")

        audio_data = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        sf.write(temp_file.name, audio_data, self.sample_rate)

        logger.info("✅ Recording saved → %s", temp_file.name)
        print("✅ Recording complete!")
        return temp_file.name

    # ------------------------------------------------------------------
    # Speaker identification
    # ------------------------------------------------------------------
    def identify_user(self, audio_path: str) -> Tuple[Optional[str], float]:
        """Identify the speaker in an audio file against enrolled users."""
        logger.info("👤 Identifying user…")
        print("👤 Identifying speaker…")

        try:
            user_id, confidence = self.speaker_id.identify_speaker(
                audio_path, self.enrolled_users
            )
            if user_id:
                logger.info("✅ User identified: %s (%.0f%%)", user_id, confidence * 100)
                print(f"✅ Identified: {user_id} (confidence: {confidence:.0%})")
            else:
                logger.info("❌ Unknown user (best score: %.0f%%)", confidence * 100)
                print(f"❌ Unknown user (best match: {confidence:.0%})")
            return user_id, confidence
        except Exception as exc:
            logger.error("Speaker identification failed: %s", exc)
            return None, 0.0

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe an audio file to text."""
        logger.info("🎙️  Transcribing audio…")
        print("🎙️  Transcribing speech…")

        try:
            result = self.asr.transcribe(audio_path)
            text = result["text"]
            logger.info("✅ Transcription: %s", text)
            print(f'✅ You said: "{text}"')
            return text
        except Exception as exc:
            logger.error("Transcription failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Query processing
    # ------------------------------------------------------------------
    def process_query(self, text: str) -> str:
        """Run the transcribed text through the chatbot / quote search."""
        logger.info("🤖 Processing query…")
        print("🤖 Searching quotes…")

        try:
            response = self.chatbot.process_message(text)
            logger.info("✅ Response generated (%d chars)", len(response))
            print("✅ Found results!")
            return response
        except Exception as exc:
            logger.error("Query processing failed: %s", exc)
            return "Sorry, I couldn't process your request."

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------
    def generate_speech(
        self,
        text: str,
        user_id: Optional[str] = None,
        output_path: str = None,
    ) -> Optional[str]:
        """
        Generate (optionally personalized) speech for the given text.

        Returns the path to the generated WAV file, or None on failure.
        """
        if user_id:
            logger.info("🔊 Generating personalized speech for %s…", user_id)
            print(f"🔊 Generating personalized response for {user_id}…")
        else:
            logger.info("🔊 Generating speech (default voice)…")
            print("🔊 Generating speech response…")

        try:
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                output_path = temp_file.name

            self.tts.synthesize_personalized(
                text,
                user_id=user_id,
                output_path=output_path,
            )

            logger.info("✅ Speech generated → %s", output_path)
            print("✅ Speech ready!")
            return output_path

        except Exception as exc:
            logger.error("Speech generation failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def play_audio(self, audio_path: str) -> None:
        """Play an audio file through the default output device."""
        logger.info("🔊 Playing: %s", audio_path)
        print("🔊 Playing response…")

        try:
            audio_data, sr = sf.read(audio_path)
            sd.play(audio_data, sr)
            sd.wait()
            logger.info("✅ Playback complete")
            print("✅ Playback complete!")
        except Exception as exc:
            logger.error("Playback failed: %s", exc)
            print(f"❌ Playback failed: {exc}")

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    def process_voice_query(
        self,
        audio_path: str = None,
        duration: int = 5,
        play_response: bool = True,
        save_response: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the complete voice pipeline end-to-end.

        Parameters
        ----------
        audio_path : str, optional
            Path to an existing audio file.  If None, records from the mic.
        duration : int
            Recording duration in seconds (used only when audio_path is None).
        play_response : bool
            Whether to play the synthesized response.
        save_response : bool
            Whether to save the response as ``response.wav`` in the CWD.

        Returns
        -------
        dict with keys: user_id, confidence, transcription, query,
                        response_text, response_audio, success
        """
        results: Dict[str, Any] = {
            "user_id": None,
            "confidence": 0.0,
            "transcription": "",
            "query": "",
            "response_text": "",
            "response_audio": None,
            "success": False,
        }

        try:
            # Step 1: obtain audio
            if audio_path is None:
                audio_path = self.record_audio(duration)
                results["recorded_audio"] = audio_path

            # Step 2: identify speaker
            user_id, confidence = self.identify_user(audio_path)
            results["user_id"] = user_id
            results["confidence"] = confidence

            # Step 3: transcribe
            transcription = self.transcribe_audio(audio_path)
            results["transcription"] = transcription
            results["query"] = transcription

            if not transcription:
                logger.error("Empty transcription — aborting pipeline")
                return results

            # Step 4: query chatbot
            response_text = self.process_query(transcription)
            results["response_text"] = response_text

            # Step 5: generate personalized speech
            output_path = "response.wav" if save_response else None
            response_audio = self.generate_speech(
                response_text,
                user_id=user_id,
                output_path=output_path,
            )
            results["response_audio"] = response_audio

            # Step 6: play response
            if play_response and response_audio:
                self.play_audio(response_audio)

            results["success"] = True
            logger.info("✅ Voice query processed successfully")
            return results

        except Exception as exc:
            logger.error("Voice query pipeline failed: %s", exc)
            results["error"] = str(exc)
            return results

    # ------------------------------------------------------------------
    # Interactive CLI
    # ------------------------------------------------------------------
    def interactive_mode(self) -> None:
        """Run an interactive voice-query REPL."""
        print("\n" + "=" * 60)
        print("🎤 WIKIQUOTE VOICE SEARCH — INTERACTIVE MODE")
        print("=" * 60)
        print(f"\n👥 Enrolled users: {len(self.enrolled_users)}")
        if self.enrolled_users:
            print("   " + ", ".join(self.enrolled_users.keys()))
        else:
            print("   ⚠️  No users enrolled yet!")
            print("   Enroll users with: python scripts/enroll_user.py")

        print("\n💡 Commands:")
        print("   'record'          — record and process a voice query")
        print("   'file <path>'     — process an existing audio file")
        print("   'quit'            — exit")
        print("=" * 60)

        while True:
            try:
                command = input("\n🎤 Enter command: ").strip().lower()

                if command in ("quit", "exit"):
                    print("👋 Goodbye!")
                    break

                elif command == "record":
                    raw = input("Duration in seconds [5]: ").strip()
                    duration = int(raw) if raw.isdigit() else 5
                    print(f"\n{'=' * 60}")
                    results = self.process_voice_query(duration=duration, play_response=True)
                    self._print_results(results)

                elif command.startswith("file "):
                    file_path = command[5:].strip()
                    if not Path(file_path).exists():
                        print(f"❌ File not found: {file_path}")
                        continue
                    print(f"\n{'=' * 60}")
                    results = self.process_voice_query(audio_path=file_path, play_response=True)
                    self._print_results(results)

                else:
                    print("❌ Unknown command.  Try 'record', 'file <path>', or 'quit'")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as exc:
                print(f"❌ Error: {exc}")

    @staticmethod
    def _print_results(results: Dict[str, Any]) -> None:
        print(f"\n📊 Results:")
        print(f"   User:     {results['user_id'] or 'Unknown'}")
        print(f"   Confidence: {results['confidence']:.0%}")
        print(f"   Query:    \"{results['query']}\"")
        print(f"   Response: {len(results['response_text'])} chars")
        print(f"   Status:   {'✅ Success' if results['success'] else '❌ Failed'}")


def main() -> None:
    print("\n🚀 Initializing Voice Orchestrator…")
    try:
        orchestrator = VoiceOrchestrator()
        orchestrator.interactive_mode()
    except Exception as exc:
        print(f"\n❌ Initialization failed: {exc}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
