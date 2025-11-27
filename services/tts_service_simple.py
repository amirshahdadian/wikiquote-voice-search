"""
Simple Text-to-Speech Service using gTTS (Google Text-to-Speech)
Fallback service when NeMo is not available
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleTTSService:
    """
    Simple TTS Service using gTTS (Google Text-to-Speech)
    Much easier to install than NeMo: pip install gtts
    """
    
    def __init__(self, device: str = "cpu", db_path: str = None):
        """Initialize simple TTS service"""
        self.device = device
        self.db_path = db_path
        logger.info("Initializing Simple TTS Service (gTTS)")
        
    def synthesize_personalized(
        self, 
        text: str, 
        output_path: str,
        user_id: str = None,
        preferences: Dict[str, Any] = None
    ):
        """
        Synthesize speech from text using gTTS
        
        Args:
            text: Text to synthesize
            output_path: Path to save audio file
            user_id: User ID (ignored in simple version)
            preferences: Voice preferences (ignored in simple version)
        """
        try:
            from gtts import gTTS
            
            logger.info(f"Synthesizing with gTTS: {text[:50]}...")
            
            # Create TTS object
            tts = gTTS(text=text, lang='en', slow=False)
            
            # Save to file
            tts.save(output_path)
            
            logger.info(f"✅ Audio saved to: {output_path}")
            
        except ImportError:
            logger.error("gTTS not installed. Install with: pip install gtts")
            raise
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            raise
