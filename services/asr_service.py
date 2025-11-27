"""
Automatic Speech Recognition (ASR) Service
Supports multiple backends: Whisper (default), NeMo, and Wav2Vec2

For best results, install optional backends:
- Whisper (default): pip install openai-whisper
- NeMo ASR (GPU, low-latency): pip install nemo_toolkit[asr]
- Wav2Vec2 (lightweight): pip install transformers librosa
"""

import logging
import tempfile
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to use hybrid service, fall back to Whisper-only if not available
try:
    from services.asr_service_hybrid import HybridASRService
    USE_HYBRID = True
except ImportError:
    USE_HYBRID = False
    import whisper


class ASRService:
    """
    ASR Service with multi-backend support (Whisper, NeMo, Wav2Vec2)
    Automatically selects best available backend or uses specified one
    """
    
    def __init__(
        self, 
        model_name: str = "base", 
        device: str = "auto",
        backend: str = "auto"
    ):
        """
        Initialize ASR service
        
        Args:
            model_name: Model size/name (backend-specific)
            device: Device to run on ('auto', 'cpu', 'cuda')
            backend: ASR backend ('auto', 'whisper', 'nemo', 'wav2vec2')
        """
        self.model_name = model_name
        self.device = device
        self.backend = backend
        
        if USE_HYBRID:
            # Use hybrid multi-backend service
            self._service = HybridASRService(
                backend=backend,
                model_name=model_name,
                device=device
            )
            logger.info(f"✅ Using Hybrid ASR (backend: {self._service.active_backend})")
        else:
            # Fallback to Whisper-only
            self.model = None
            logger.info(f"⚠️  Hybrid ASR not available, using Whisper only")
            logger.info(f"Initializing Whisper ASR with model '{model_name}' on {device}")
        
    def load_model(self):
        """Load ASR model (no-op if using hybrid service)"""
        if USE_HYBRID:
            pass  # Hybrid service loads models on-demand
        else:
            if self.model is None:
                logger.info(f"Loading Whisper model '{self.model_name}' on {self.device}...")
                self.model = whisper.load_model(self.model_name, device=self.device)
                logger.info(f"✅ Whisper model loaded successfully")
    
    def transcribe(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribe audio file to text
        
        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en', 'fa')
            
        Returns:
            dict with 'text', 'language', 'backend', 'normalized_text', and metadata
        """
        if USE_HYBRID:
            result = self._service.transcribe(audio_path, language)
            # Add normalization
            result['normalized_text'] = self.normalize_command(result['text'])
            return result
        else:
            # Fallback to Whisper-only
            self.load_model()
            
            logger.info(f"Transcribing audio: {audio_path}")
            
            options = {
                'fp16': False,
                'temperature': 0.0,
                'best_of': 5,
                'beam_size': 5,
                'initial_prompt': 'Find quotes about courage, wisdom, love, and happiness. Show me inspirational quotes.'
            }
            if language:
                options['language'] = language
            
            result = self.model.transcribe(audio_path, **options)
            
            transcribed_text = result['text'].strip()
            normalized_text = self.normalize_command(transcribed_text)
            
            logger.info(f"Transcription: {transcribed_text}")
            logger.info(f"Normalized: {normalized_text}")
            
            return {
                'text': transcribed_text,
                'normalized_text': normalized_text,
                'language': result.get('language', 'unknown'),
                'backend': 'whisper',
                'segments': result.get('segments', []),
                'full_result': result
            }
    
    def transcribe_bytes(self, audio_bytes: bytes, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribe audio from bytes
        
        Args:
            audio_bytes: Audio data as bytes
            language: Optional language code
            
        Returns:
            dict with transcription results
        """
        if USE_HYBRID:
            result = self._service.transcribe_bytes(audio_bytes, language)
            result['normalized_text'] = self.normalize_command(result['text'])
            return result
        else:
            # Fallback to Whisper-only
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_path = tmp_file.name
            
            try:
                result = self.transcribe(tmp_path, language=language)
                return result
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
    
    def normalize_command(self, text: str) -> str:
        """
        Normalize ASR transcription for quote search commands.
        Fixes common speech recognition mistakes.
        
        Args:
            text: Raw transcription
            
        Returns:
            Normalized command text
        """
        text = text.lower().strip()
        
        # AGGRESSIVE: Common ASR mistakes for "quotes" - replace ANYWHERE in text
        quote_variations = [
            ('codes', 'quotes'),
            ('code', 'quotes'),
            ('coats', 'quotes'),
            ('coat', 'quotes'),
            ('courts', 'quotes'),
            ('court', 'quotes'),
            ('colds', 'quotes'),
            ('cold', 'quotes'),
            ('cords', 'quotes'),
            ('cord', 'quotes'),
            ('cotes', 'quotes'),
            ('cote', 'quotes'),
            ('quoads', 'quotes'),
            ('quoad', 'quotes'),
        ]
        
        for wrong, correct in quote_variations:
            # Replace ANYWHERE (not just in specific patterns)
            text = re.sub(rf'\b{wrong}\b', correct, text, flags=re.IGNORECASE)
        
        # Additional pattern-based fixes for safety
        text = re.sub(
            r'\b(find|show|give|get|search)\s+(any|some|me)\s+(stone|story|store)\b',
            r'\1 \2 quotes',
            text,
            flags=re.IGNORECASE
        )
        
        # Remove filler words common in speech
        filler_words = [
            r'\bum+\b', r'\buh+\b', r'\blike\b', r'\byou know\b',
            r'\bI mean\b', r'\bso\b', r'\bwell\b', r'\bokay\b',
            r'\balright\b', r'\bactually\b'
        ]
        
        for filler in filler_words:
            text = re.sub(filler, '', text, flags=re.IGNORECASE)
        
        # Normalize command phrases
        command_normalizations = {
            r'find me some': 'find',
            r'can you find': 'find',
            r'I want to find': 'find',
            r'I want': 'find',
            r'show me some': 'show me',
            r'give me some': 'give me',
            r'search for': 'find',
            r'look for': 'find',
        }
        
        for pattern, replacement in command_normalizations.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Extract core topic by removing command words
        command_words = ['find', 'show', 'give', 'me', 'quotes', 'quote', 'about', 'on', 'for']
        words = text.split()
        
        # Keep only meaningful words
        topic_words = [w for w in words if w not in command_words and len(w) > 2]
        
        if topic_words:
            return ' '.join(topic_words)
        
        # Clean up whitespace
        text = ' '.join(text.split())
        
        return text
    
    def switch_backend(self, backend: str) -> None:
        """Switch to a different ASR backend at runtime"""
        if USE_HYBRID:
            self._service.switch_backend(backend)
        else:
            logger.warning("Backend switching only available with hybrid service")
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get information about active backend"""
        if USE_HYBRID:
            return self._service.get_backend_info()
        else:
            return {
                'active_backend': 'whisper',
                'available_backends': {'whisper': True},
                'device': self.device,
                'model_name': self.model_name
            }
