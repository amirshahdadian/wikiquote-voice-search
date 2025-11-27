#!/usr/bin/env python3
"""
Quick test script for Hybrid ASR Service
Tests all available backends and compares results
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.asr_service import ASRService


def test_hybrid_asr():
    """Test hybrid ASR with different backends"""
    
    print("🎤 Testing Hybrid ASR Service")
    print("=" * 60)
    
    # Test with auto backend selection
    print("\n1️⃣  Testing AUTO backend selection:")
    print("-" * 60)
    asr_auto = ASRService(backend="auto", model_name="tiny")
    info = asr_auto.get_backend_info()
    print(f"✅ Active backend: {info['active_backend']}")
    print(f"   Device: {info['device']}")
    print(f"   Available backends: {list(info['available_backends'].keys())}")
    
    # Test each backend individually
    backends_to_test = ['whisper', 'nemo', 'wav2vec2']
    
    for backend in backends_to_test:
        print(f"\n2️⃣  Testing {backend.upper()} backend:")
        print("-" * 60)
        try:
            asr = ASRService(backend=backend, model_name="tiny")
            info = asr.get_backend_info()
            if info['available_backends'].get(backend, False):
                print(f"✅ {backend.upper()} is available and ready")
                print(f"   Device: {info['device']}")
                # Would transcribe test audio here if we had a test file
            else:
                print(f"⚠️  {backend.upper()} is not installed")
                print(f"   Install with: pip install {get_install_command(backend)}")
        except Exception as e:
            print(f"❌ {backend.upper()} failed: {e}")
    
    # Summary
    print("\n📊 SUMMARY:")
    print("=" * 60)
    available_count = sum(1 for v in info['available_backends'].values() if v)
    print(f"Available backends: {available_count}/3")
    
    if available_count == 3:
        print("✅ All backends installed - you have the best setup!")
    elif available_count >= 1:
        print("✅ At least one backend available - system will work")
        print("💡 Tip: Install more backends for better performance and fallback")
    else:
        print("❌ No backends available - please install at least Whisper")
    
    print("\n🚀 Recommendations:")
    if not info['available_backends'].get('whisper', False):
        print("   pip install openai-whisper  # Required")
    if not info['available_backends'].get('nemo', False):
        print("   pip install nemo_toolkit[asr]  # For GPU acceleration")
    if not info['available_backends'].get('wav2vec2', False):
        print("   pip install transformers librosa  # For fine-tuning")


def get_install_command(backend):
    """Get pip install command for a backend"""
    commands = {
        'whisper': 'openai-whisper',
        'nemo': 'nemo_toolkit[asr]',
        'wav2vec2': 'transformers librosa'
    }
    return commands.get(backend, backend)


def test_transcription(audio_path: str):
    """Test actual transcription with a sample audio file"""
    print(f"\n🎵 Testing transcription with: {audio_path}")
    print("=" * 60)
    
    if not Path(audio_path).exists():
        print(f"❌ Audio file not found: {audio_path}")
        print("   Create a test audio file or skip this test")
        return
    
    backends = ['auto', 'whisper', 'nemo', 'wav2vec2']
    
    for backend in backends:
        try:
            print(f"\nTesting {backend.upper()}:")
            print("-" * 40)
            asr = ASRService(backend=backend, model_name="tiny")
            result = asr.transcribe(audio_path)
            
            print(f"✅ Backend used: {result['backend']}")
            print(f"   Transcription: {result['text']}")
            print(f"   Language: {result.get('language', 'unknown')}")
            
        except Exception as e:
            print(f"⚠️  {backend.upper()} skipped: {e}")


if __name__ == "__main__":
    # Test backend availability
    test_hybrid_asr()
    
    # Test transcription if audio file provided
    if len(sys.argv) > 1:
        audio_path = sys.argv[1]
        test_transcription(audio_path)
    else:
        print("\n" + "=" * 60)
        print("💡 To test transcription, run:")
        print(f"   python {sys.argv[0]} path/to/audio.wav")
        print("=" * 60)
