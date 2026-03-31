"""
Hybrid Automatic Speech Recognition (ASR) Service
Supports multiple backends: Whisper, Wav2Vec2, and NVIDIA NeMo
with intelligent routing and automatic fallback
"""

import logging
import tempfile
import os
import importlib.util
from pathlib import Path
from typing import Optional, Dict, Any

from src.wikiquote_voice.config import Config
from src.wikiquote_voice.nemo_compat import (
    load_nemo_asr_model,
    resolve_nemo_device,
    resolve_runtime_device,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HybridASRService:
    """
    Multi-backend ASR Service with automatic backend selection and fallback
    
    Supported backends:
    - whisper: OpenAI Whisper (default, best multilingual)
    - nemo: NVIDIA NeMo ASR (best for low-latency GPU inference)
    - wav2vec2: Hugging Face Wav2Vec2 (lightweight, fine-tunable)
    """
    
    def __init__(
        self, 
        backend: str = "auto",
        model_name: str = "base",
        device: str = "auto"
    ):
        """
        Initialize hybrid ASR service
        
        Args:
            backend: ASR backend ('auto', 'whisper', 'nemo', 'wav2vec2')
            model_name: Model size/name (backend-specific)
            device: Device to run on ('auto', 'cpu', 'cuda')
        """
        self.backend = backend
        self.model_name = model_name
        self.device = self._detect_device() if device == "auto" else resolve_runtime_device(device, allow_mps=True)
        
        # Available backends
        self.backends_available = self._check_backends()
        
        # Select backend
        if backend == "auto":
            self.active_backend = self._select_best_backend()
        else:
            self.active_backend = backend
        
        logger.info(f"🎤 Hybrid ASR initialized: backend={self.active_backend}, device={self.device}")
        logger.info(f"📦 Available backends: {list(self.backends_available.keys())}")
        
        # Backend instances
        self._whisper_model = None
        self._nemo_model = None
        self._wav2vec2_model = None
    
    def _detect_device(self) -> str:
        """Detect best available device without importing torch eagerly."""
        device = resolve_runtime_device("auto", allow_mps=True)
        logger.info("ℹ️  Using %s", device.upper())
        return device
    
    def _check_backends(self) -> Dict[str, bool]:
        """Check which backends are available"""
        available = {}
        
        # Check Whisper
        if importlib.util.find_spec("whisper") is not None:
            available['whisper'] = True
        else:
            available['whisper'] = False
            logger.warning("⚠️  Whisper not available (pip install openai-whisper)")
        
        # Check NeMo
        if importlib.util.find_spec("nemo.collections.asr") is not None:
            available['nemo'] = True
        else:
            available['nemo'] = False
            logger.info("ℹ️  NeMo ASR not available (optional)")
        
        # Check Wav2Vec2
        if (
            importlib.util.find_spec("transformers") is not None
            and importlib.util.find_spec("librosa") is not None
        ):
            available['wav2vec2'] = True
        else:
            available['wav2vec2'] = False
            logger.info("ℹ️  Wav2Vec2 not available (optional)")
        
        return available
    
    def _select_best_backend(self) -> str:
        """Automatically select best available backend"""
        # Priority order based on capabilities and device
        if self.device == "cuda" and self.backends_available.get('nemo', False):
            logger.info("🚀 Selected NeMo ASR (GPU available, best latency)")
            return "nemo"
        elif self.backends_available.get('whisper', False):
            logger.info("🎯 Selected Whisper (best multilingual accuracy)")
            return "whisper"
        elif self.backends_available.get('wav2vec2', False):
            logger.info("⚡ Selected Wav2Vec2 (lightweight fallback)")
            return "wav2vec2"
        else:
            raise RuntimeError("No ASR backend available! Install at least one: openai-whisper, nemo_toolkit, or transformers")
    
    def transcribe(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribe audio file using active backend with automatic fallback
        
        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en', 'fa')
            
        Returns:
            dict with 'text', 'language', 'backend', and other metadata
        """
        logger.info(f"🎤 Transcribing with {self.active_backend} backend: {audio_path}")
        
        # Try active backend
        try:
            if self.active_backend == "whisper":
                return self._transcribe_whisper(audio_path, language)
            elif self.active_backend == "nemo":
                return self._transcribe_nemo(audio_path, language)
            elif self.active_backend == "wav2vec2":
                return self._transcribe_wav2vec2(audio_path, language)
            else:
                raise ValueError(f"Unknown backend: {self.active_backend}")
        
        except Exception as e:
            logger.error(f"❌ {self.active_backend} failed: {e}")
            
            # Try fallback backends
            fallback_order = ['whisper', 'wav2vec2', 'nemo']
            fallback_order.remove(self.active_backend)
            
            for fallback_backend in fallback_order:
                if self.backends_available.get(fallback_backend, False):
                    logger.warning(f"🔄 Falling back to {fallback_backend}")
                    try:
                        if fallback_backend == "whisper":
                            return self._transcribe_whisper(audio_path, language)
                        elif fallback_backend == "nemo":
                            return self._transcribe_nemo(audio_path, language)
                        elif fallback_backend == "wav2vec2":
                            return self._transcribe_wav2vec2(audio_path, language)
                    except Exception as fallback_error:
                        logger.error(f"❌ {fallback_backend} fallback failed: {fallback_error}")
                        continue
            
            raise RuntimeError("All ASR backends failed")
    
    def _transcribe_whisper(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe using OpenAI Whisper"""
        import whisper
        
        if self._whisper_model is None:
            logger.info(f"Loading Whisper model '{self.model_name}'...")
            self._whisper_model = whisper.load_model(self.model_name, device=self.device)
        
        # Add prompt to guide Whisper toward correct vocabulary
        options = {
            'temperature': 0.0,  # More deterministic
            'initial_prompt': 'Find quotes about courage, wisdom, love, and happiness. Show me inspirational quotes.'
        }
        if language:
            options['language'] = language
        
        result = self._whisper_model.transcribe(audio_path, **options)
        
        return {
            'text': result['text'].strip(),
            'language': result.get('language', 'unknown'),
            'backend': 'whisper',
            'confidence': None,  # Whisper doesn't provide confidence
            'segments': result.get('segments', []),
            'full_result': result
        }
    
    def _transcribe_nemo(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe using NVIDIA NeMo"""
        if self._nemo_model is None:
            configured_model = (
                Config.NEMO_ASR_MULTILINGUAL_MODEL
                if language and language != "en" and Config.NEMO_ASR_MULTILINGUAL_MODEL
                else Config.NEMO_ASR_MODEL
            )
            logger.info(
                "Loading NeMo 2.x ASR model '%s' on %s...",
                configured_model,
                self.device,
            )
            self._nemo_model = load_nemo_asr_model(self.device, language=language)
        
        # Transcribe
        transcriptions = self._nemo_model.transcribe([audio_path], batch_size=1)
        text = transcriptions[0] if transcriptions else ""
        if hasattr(text, "text"):
            text = text.text
        elif not isinstance(text, str):
            text = str(text)
        
        return {
            'text': text.strip(),
            'language': language or 'en',
            'backend': 'nemo',
            'confidence': None,  # Could extract from logits if needed
            'segments': [],
            'full_result': {'text': text}
        }
    
    def _transcribe_wav2vec2(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe using Wav2Vec2"""
        import torch
        from transformers import AutoProcessor, Wav2Vec2ForCTC
        import librosa
        
        if self._wav2vec2_model is None:
            # Use base English model (can be changed to other languages)
            model_id = "facebook/wav2vec2-base-960h"
            logger.info(f"Loading Wav2Vec2 model '{model_id}'...")
            self._wav2vec2_model = Wav2Vec2ForCTC.from_pretrained(model_id)
            self._wav2vec2_processor = AutoProcessor.from_pretrained(model_id)
            
            if self.device in {"cuda", "mps"}:
                self._wav2vec2_model = self._wav2vec2_model.to(self.device)
        
        # Load audio
        audio, sr = librosa.load(audio_path, sr=16000)
        
        # Process
        inputs = self._wav2vec2_processor(audio, sampling_rate=16000, return_tensors="pt", padding=True)
        
        if self.device in {"cuda", "mps"}:
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Inference
        with torch.no_grad():
            logits = self._wav2vec2_model(inputs.input_values).logits
        
        predicted_ids = torch.argmax(logits, dim=-1)
        transcription = self._wav2vec2_processor.batch_decode(predicted_ids)[0]
        
        return {
            'text': transcription.strip(),
            'language': language or 'en',
            'backend': 'wav2vec2',
            'confidence': None,
            'segments': [],
            'full_result': {'text': transcription}
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
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_path = tmp_file.name
        
        try:
            result = self.transcribe(tmp_path, language=language)
            return result
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    def switch_backend(self, backend: str) -> None:
        """
        Switch to a different backend at runtime
        
        Args:
            backend: Target backend ('whisper', 'nemo', 'wav2vec2')
        """
        if not self.backends_available.get(backend, False):
            raise ValueError(f"Backend '{backend}' is not available")
        
        logger.info(f"🔄 Switching from {self.active_backend} to {backend}")
        self.active_backend = backend
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get information about active backend and available backends"""
        return {
            'active_backend': self.active_backend,
            'available_backends': self.backends_available,
            'device': self.device,
            'model_name': self.model_name
        }


# Backward compatibility: alias to the original ASRService
class ASRService(HybridASRService):
    """
    ASR Service (alias to HybridASRService for backward compatibility)
    """
    pass
