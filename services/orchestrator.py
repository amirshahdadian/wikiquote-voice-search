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
    Orchestrates complete voice interaction pipeline
    Handles multi-user voice queries with personalized responses
    """
    
    def __init__(self, sample_rate: int = 16000, threshold: float = 0.7):
        """
        Initialize voice orchestrator
        
        Args:
            sample_rate: Audio sample rate for recording
            threshold: Speaker identification threshold
        """
        self.sample_rate = sample_rate
        self.threshold = threshold
        
        # Initialize services
        logger.info("Initializing Voice Orchestrator...")
        
        # Speaker ID
        self.speaker_id = SpeakerIdentificationService(threshold=threshold)
        logger.info("✅ Speaker ID initialized")
        
        # ASR
        self.asr = ASRService(model_name='base')
        logger.info("✅ ASR initialized")
        
        # Chatbot
        self.chatbot = ChatbotService()
        logger.info("✅ Chatbot initialized")
        
        # TTS
        db_path = Path(Config.DATA_DIR) / "wikiquote_voice.db"
        self.tts = TTSService(device="cpu", db_path=str(db_path))
        logger.info("✅ TTS initialized")
        
        # Load enrolled users
        embeddings_dir = Path(Config.DATA_DIR) / "embeddings"
        self.enrolled_users = self.speaker_id.get_all_enrolled_users(str(embeddings_dir))
        logger.info(f"✅ Loaded {len(self.enrolled_users)} enrolled users")
        
        logger.info("🎉 Voice Orchestrator ready!")
    
    def record_audio(self, duration: int = 5) -> str:
        """
        Record audio from microphone
        
        Args:
            duration: Recording duration in seconds
            
        Returns:
            Path to recorded audio file
        """
        logger.info(f"🎤 Recording for {duration} seconds...")
        print(f"🎤 Speak now! Recording for {duration} seconds...")
        
        try:
            # Record audio
            audio_data = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32'
            )
            sd.wait()  # Wait for recording to complete
            
            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            sf.write(temp_file.name, audio_data, self.sample_rate)
            
            logger.info(f"✅ Recording saved to: {temp_file.name}")
            print(f"✅ Recording complete!")
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Recording failed: {e}")
            raise
    
    def identify_user(self, audio_path: str) -> Tuple[Optional[str], float]:
        """
        Identify user from audio
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Tuple of (user_id, confidence) or (None, score) if unknown
        """
        logger.info("👤 Identifying user...")
        print("👤 Identifying speaker...")
        
        try:
            user_id, confidence = self.speaker_id.identify_speaker(
                audio_path,
                self.enrolled_users
            )
            
            if user_id:
                logger.info(f"✅ User identified: {user_id} ({confidence:.2%})")
                print(f"✅ Identified: {user_id} (confidence: {confidence:.0%})")
            else:
                logger.info(f"❌ Unknown user (best score: {confidence:.2%})")
                print(f"❌ Unknown user (best match: {confidence:.0%})")
            
            return user_id, confidence
            
        except Exception as e:
            logger.error(f"Speaker identification failed: {e}")
            return None, 0.0
    
    def transcribe_audio(self, audio_path: str) -> str:
        """
        Transcribe audio to text
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Transcribed text
        """
        logger.info("🎙️  Transcribing audio...")
        print("🎙️  Transcribing speech...")
        
        try:
            result = self.asr.transcribe(audio_path)
            text = result['text']
            
            logger.info(f"✅ Transcription: {text}")
            print(f"✅ You said: \"{text}\"")
            
            return text
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return ""
    
    def process_query(self, text: str) -> str:
        """
        Process query through chatbot
        
        Args:
            text: Query text
            
        Returns:
            Chatbot response
        """
        logger.info("🤖 Processing query...")
        print("🤖 Searching quotes...")
        
        try:
            response = self.chatbot.process_message(text)
            
            logger.info(f"✅ Response generated ({len(response)} chars)")
            print(f"✅ Found results!")
            
            return response
            
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return "Sorry, I couldn't process your request."
    
    def generate_speech(
        self, 
        text: str, 
        user_id: Optional[str] = None,
        output_path: str = None
    ) -> str:
        """
        Generate personalized speech response
        
        Args:
            text: Text to synthesize
            user_id: User ID for personalization (None for default)
            output_path: Optional path to save audio
            
        Returns:
            Path to generated audio file
        """
        if user_id:
            logger.info(f"🔊 Generating personalized speech for {user_id}...")
            print(f"🔊 Generating personalized response for {user_id}...")
        else:
            logger.info("🔊 Generating speech with default voice...")
            print("🔊 Generating speech response...")
        
        try:
            # Create output path if not provided
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
                output_path = temp_file.name
            
            # Generate speech
            if user_id:
                self.tts.synthesize_personalized(
                    text,
                    user_id=user_id,
                    output_path=output_path
                )
            else:
                self.tts.synthesize(
                    text,
                    output_path=output_path
                )
            
            logger.info(f"✅ Speech generated: {output_path}")
            print(f"✅ Speech ready!")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Speech generation failed: {e}")
            return None
    
    def play_audio(self, audio_path: str):
        """
        Play audio file
        
        Args:
            audio_path: Path to audio file
        """
        logger.info(f"🔊 Playing audio: {audio_path}")
        print("🔊 Playing response...")
        
        try:
            # Load audio
            audio_data, sample_rate = sf.read(audio_path)
            
            # Play
            sd.play(audio_data, sample_rate)
            sd.wait()
            
            logger.info("✅ Playback complete")
            print("✅ Playback complete!")
            
        except Exception as e:
            logger.error(f"Playback failed: {e}")
            print(f"❌ Playback failed: {e}")
    
    def process_voice_query(
        self,
        audio_path: str = None,
        duration: int = 5,
        play_response: bool = True,
        save_response: bool = False
    ) -> Dict[str, Any]:
        """
        Process complete voice query pipeline
        
        Args:
            audio_path: Path to audio file (or None to record)
            duration: Recording duration if audio_path is None
            play_response: Whether to play the response
            save_response: Whether to save response to file
            
        Returns:
            Dictionary with pipeline results
        """
        results = {
            'user_id': None,
            'confidence': 0.0,
            'transcription': '',
            'query': '',
            'response_text': '',
            'response_audio': None,
            'success': False
        }
        
        try:
            # Step 1: Record or load audio
            if audio_path is None:
                audio_path = self.record_audio(duration)
                results['recorded_audio'] = audio_path
            
            # Step 2: Identify speaker
            user_id, confidence = self.identify_user(audio_path)
            results['user_id'] = user_id
            results['confidence'] = confidence
            
            # Step 3: Transcribe audio
            transcription = self.transcribe_audio(audio_path)
            results['transcription'] = transcription
            results['query'] = transcription
            
            if not transcription:
                logger.error("No transcription available")
                return results
            
            # Step 4: Process query
            response_text = self.process_query(transcription)
            results['response_text'] = response_text
            
            # Step 5: Generate personalized speech
            output_path = "response.wav" if save_response else None
            response_audio = self.generate_speech(
                response_text,
                user_id=user_id,
                output_path=output_path
            )
            results['response_audio'] = response_audio
            
            # Step 6: Play response
            if play_response and response_audio:
                self.play_audio(response_audio)
            
            results['success'] = True
            logger.info("✅ Voice query processed successfully")
            
            return results
            
        except Exception as e:
            logger.error(f"Voice query processing failed: {e}")
            results['error'] = str(e)
            return results
    
    def interactive_mode(self):
        """Run interactive voice query loop"""
        print("\n" + "="*60)
        print("🎤 WIKIQUOTE VOICE SEARCH - INTERACTIVE MODE")
        print("="*60)
        print(f"\n👥 Enrolled users: {len(self.enrolled_users)}")
        if self.enrolled_users:
            print(f"   {', '.join(self.enrolled_users.keys())}")
        else:
            print("   ⚠️  No users enrolled yet!")
            print("   Enroll users with: python scripts/enroll_user.py")
        
        print("\n💡 Commands:")
        print("   'record' - Record and process voice query")
        print("   'file <path>' - Process audio file")
        print("   'quit' - Exit")
        print("="*60)
        
        while True:
            try:
                command = input("\n🎤 Enter command: ").strip().lower()
                
                if command == 'quit' or command == 'exit':
                    print("👋 Goodbye!")
                    break
                
                elif command == 'record':
                    duration = input("Duration (seconds, default 5): ").strip()
                    duration = int(duration) if duration.isdigit() else 5
                    
                    print(f"\n{'='*60}")
                    results = self.process_voice_query(
                        duration=duration,
                        play_response=True
                    )
                    print(f"{'='*60}")
                    
                    # Display results
                    print(f"\n📊 Results:")
                    print(f"   User: {results['user_id'] or 'Unknown'}")
                    print(f"   Confidence: {results['confidence']:.0%}")
                    print(f"   Query: \"{results['query']}\"")
                    print(f"   Response length: {len(results['response_text'])} chars")
                    print(f"   Status: {'✅ Success' if results['success'] else '❌ Failed'}")
                
                elif command.startswith('file '):
                    file_path = command[5:].strip()
                    
                    if not Path(file_path).exists():
                        print(f"❌ File not found: {file_path}")
                        continue
                    
                    print(f"\n{'='*60}")
                    results = self.process_voice_query(
                        audio_path=file_path,
                        play_response=True
                    )
                    print(f"{'='*60}")
                    
                    # Display results
                    print(f"\n📊 Results:")
                    print(f"   User: {results['user_id'] or 'Unknown'}")
                    print(f"   Confidence: {results['confidence']:.0%}")
                    print(f"   Query: \"{results['query']}\"")
                    print(f"   Response length: {len(results['response_text'])} chars")
                    print(f"   Status: {'✅ Success' if results['success'] else '❌ Failed'}")
                
                else:
                    print("❌ Unknown command. Try 'record', 'file <path>', or 'quit'")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")


def main():
    """Main entry point"""
    print("\n🚀 Initializing Voice Orchestrator...")
    
    try:
        orchestrator = VoiceOrchestrator()
        orchestrator.interactive_mode()
        
    except Exception as e:
        print(f"\n❌ Failed to initialize: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
