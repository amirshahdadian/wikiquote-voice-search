"""
Text-to-Speech (TTS) Service using NVIDIA NeMo FastPitch + HiFiGAN
Supports personalized voice output based on user preferences
"""

import logging
import numpy as np
import soundfile as sf
from pathlib import Path
import tempfile
import sqlite3
from typing import Optional, Dict, Any
import torch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TTSService:
    """
    Personalized TTS Service using NVIDIA NeMo FastPitch (spectrogram generator) + HiFiGAN (vocoder)
    Supports user-specific voice customization
    """
    
    def __init__(self, device: str = "cpu", db_path: str = None):
        """
        Initialize TTS service with FastPitch and HiFiGAN models
        
        Args:
            device: Device to run on (cpu or cuda)
            db_path: Path to SQLite database with user preferences
        """
        self.device = device
        self.db_path = db_path
        self.spec_generator = None
        self.vocoder = None
        logger.info(f"Initializing Personalized TTS Service on {device}")
        
    def load_models(self):
        """Load FastPitch and HiFiGAN models"""
        if self.spec_generator is None or self.vocoder is None:
            try:
                from nemo.collections.tts.models import FastPitchModel, HifiGanModel
                
                logger.info("Loading NeMo TTS models on cpu...")
                
                # Load FastPitch (spectrogram generator)
                logger.info("Loading FastPitch model...")
                self.spec_generator = FastPitchModel.from_pretrained("nvidia/tts_en_fastpitch")
                self.spec_generator.eval()
                
                # Load HiFiGAN (vocoder)
                logger.info("Loading HiFiGAN vocoder...")
                self.vocoder = HifiGanModel.from_pretrained("nvidia/tts_hifigan")
                self.vocoder.eval()
                
                logger.info("✅ TTS models loaded successfully")
                
            except Exception as e:
                logger.error(f"Failed to load TTS models: {e}")
                raise
    
    def synthesize(self, text: str, output_path: str = None, sample_rate: int = 22050) -> np.ndarray:
        """
        Synthesize speech from text
        
        Args:
            text: Text to synthesize
            output_path: Optional path to save audio file
            sample_rate: Audio sample rate
            
        Returns:
            Audio waveform as numpy array
        """
        self.load_models()
        
        logger.info(f"Synthesizing: {text}")
        
        try:
            # Parse text with FastPitch
            parsed = self.spec_generator.parse(text)
            
            # Generate spectrogram
            spectrogram = self.spec_generator.generate_spectrogram(tokens=parsed)
            
            # Convert spectrogram to audio with HiFiGAN
            with torch.no_grad():
                audio = self.vocoder.convert_spectrogram_to_audio(spec=spectrogram)
                
                # Convert to numpy array
                if hasattr(audio, 'cpu'):
                    audio_np = audio.detach().cpu().numpy().squeeze()
                else:
                    audio_np = np.array(audio).squeeze()
            
            # Save to file if path provided
            if output_path:
                sf.write(output_path, audio_np, sample_rate)
                logger.info(f"Audio saved to: {output_path}")
            
            logger.info("✅ Speech synthesis complete")
            return audio_np
            
        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            raise
    
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Load TTS preferences for a specific user from database
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary of user preferences
        """
        if not self.db_path:
            logger.warning("No database path provided, using defaults")
            return self._get_default_preferences()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT pitch_scale, speaking_rate, energy_scale, style
                FROM user_tts_preferences
                WHERE user_id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                prefs = {
                    'pitch_scale': row[0],
                    'speaking_rate': row[1],
                    'energy_scale': row[2],
                    'style': row[3]
                }
                logger.info(f"Loaded preferences for user '{user_id}': {prefs}")
                return prefs
            else:
                logger.warning(f"No preferences found for user '{user_id}', using defaults")
                return self._get_default_preferences()
                
        except Exception as e:
            logger.error(f"Failed to load user preferences: {e}")
            return self._get_default_preferences()
    
    def _get_default_preferences(self) -> Dict[str, Any]:
        """Get default TTS preferences"""
        return {
            'pitch_scale': 1.0,
            'speaking_rate': 1.0,
            'energy_scale': 1.0,
            'style': 'neutral'
        }
    
    def synthesize_personalized(
        self, 
        text: str, 
        user_id: str = None,
        output_path: str = None, 
        sample_rate: int = 22050,
        preferences: Dict[str, Any] = None
    ) -> np.ndarray:
        """
        Synthesize speech with personalized voice settings
        
        Args:
            text: Text to synthesize
            user_id: User ID to load preferences for
            output_path: Optional path to save audio file
            sample_rate: Audio sample rate
            preferences: Optional manual preferences (overrides user_id)
            
        Returns:
            Audio waveform as numpy array
        """
        self.load_models()
        
        # Load user preferences
        if preferences is None:
            if user_id:
                preferences = self.get_user_preferences(user_id)
                logger.info(f"Synthesizing for user '{user_id}' with custom preferences")
            else:
                preferences = self._get_default_preferences()
                logger.info("Synthesizing with default preferences")
        
        logger.info(f"Preferences: pitch={preferences['pitch_scale']}, "
                   f"rate={preferences['speaking_rate']}, "
                   f"energy={preferences['energy_scale']}, "
                   f"style={preferences['style']}")
        
        logger.info(f"Synthesizing: {text}")
        
        try:
            # Parse text with FastPitch
            parsed = self.spec_generator.parse(text)
            
            # Generate spectrogram with personalized settings
            spectrogram = self.spec_generator.generate_spectrogram(
                tokens=parsed,
                pitch_shift=preferences['pitch_scale'],
                pace=1.0 / preferences['speaking_rate']  # Inverse for pace
            )
            
            # Convert spectrogram to audio with HiFiGAN
            with torch.no_grad():
                audio = self.vocoder.convert_spectrogram_to_audio(spec=spectrogram)
                
                # Convert to numpy array
                if hasattr(audio, 'cpu'):
                    audio_np = audio.detach().cpu().numpy().squeeze()
                else:
                    audio_np = np.array(audio).squeeze()
            
            # Apply energy scaling (volume)
            audio_np = audio_np * preferences['energy_scale']
            
            # Clip to prevent overflow
            audio_np = np.clip(audio_np, -1.0, 1.0)
            
            # Save to file if path provided
            if output_path:
                sf.write(output_path, audio_np, sample_rate)
                logger.info(f"Audio saved to: {output_path}")
            
            logger.info("✅ Personalized speech synthesis complete")
            return audio_np
            
        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            # Fallback to default synthesis
            logger.warning("Falling back to default synthesis")
            return self.synthesize(text, output_path, sample_rate)
    
    def synthesize_to_bytes(self, text: str, sample_rate: int = 22050) -> bytes:
        """
        Synthesize speech and return as bytes
        
        Args:
            text: Text to synthesize
            sample_rate: Audio sample rate
            
        Returns:
            Audio data as bytes
        """
        # Synthesize to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Generate audio
            with torch.no_grad():
                self.synthesize(text, output_path=tmp_path, sample_rate=sample_rate)
            
            # Read as bytes
            with open(tmp_path, 'rb') as f:
                audio_bytes = f.read()
            
            return audio_bytes
            
        finally:
            # Clean up temp file
            import os
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    def synthesize_personalized_to_bytes(
        self, 
        text: str, 
        user_id: str = None,
        sample_rate: int = 22050,
        preferences: Dict[str, Any] = None
    ) -> bytes:
        """
        Synthesize personalized speech and return as bytes
        
        Args:
            text: Text to synthesize
            user_id: User ID for preferences
            sample_rate: Audio sample rate
            preferences: Optional manual preferences
            
        Returns:
            Audio data as bytes
        """
        # Synthesize to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Generate personalized audio
            self.synthesize_personalized(
                text, 
                user_id=user_id,
                output_path=tmp_path, 
                sample_rate=sample_rate,
                preferences=preferences
            )
            
            # Read as bytes
            with open(tmp_path, 'rb') as f:
                audio_bytes = f.read()
            
            return audio_bytes
            
        finally:
            # Clean up temp file
            import os
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def demo_personalized_tts():
    """Demo personalized TTS functionality"""
    from src.wikiquote_voice.config import Config
    
    print("\n🔊 Personalized TTS Demo")
    print("=" * 60)
    
    try:
        # Initialize TTS service
        db_path = Path(Config.DATA_DIR) / "wikiquote_voice.db"
        tts = TTSService(device="cpu", db_path=str(db_path))
        
        # Test text
        test_text = "Welcome to Wikiquote Voice Search. How can I help you today?"
        
        # List enrolled users
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_id, pitch_scale, speaking_rate, style
            FROM user_tts_preferences
        """)
        
        users = cursor.fetchall()
        conn.close()
        
        if not users:
            print("\n⚠️  No users with TTS preferences found!")
            print("Please enroll users first using: python scripts/enroll_user.py")
            return
        
        print(f"\n✅ Found {len(users)} users with TTS preferences:")
        for user_id, pitch, rate, style in users:
            print(f"\n  User: {user_id}")
            print(f"  Pitch: {pitch}x, Rate: {rate}x, Style: {style}")
            
            # Generate speech
            output_file = f"demo_{user_id}.wav"
            print(f"  Generating: {output_file}")
            
            tts.synthesize_personalized(
                test_text,
                user_id=user_id,
                output_path=output_file
            )
            
            print(f"  ✅ Saved to: {output_file}")
        
        print("\n🎉 Demo complete! Check the audio files.")
        
    except ImportError:
        print("\n❌ NeMo not installed!")
        print("Install with: pip install nemo_toolkit[asr,tts]==1.21.0")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    demo_personalized_tts()
