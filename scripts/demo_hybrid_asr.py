#!/usr/bin/env python3
"""Show available ASR backends and optionally transcribe a sample file."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.asr_service import ASRService


def get_install_command(backend: str) -> str:
    commands = {
        "whisper": "openai-whisper",
        "nemo": '"nemo-toolkit[asr]>=2.4,<3"',
        "wav2vec2": "transformers librosa",
    }
    return commands.get(backend, backend)


def run_backend_demo() -> None:
    print("Hybrid ASR backend demo")
    print("=" * 60)

    print("\nAUTO backend selection")
    print("-" * 60)
    asr_auto = ASRService(backend="auto", model_name="tiny")
    info = asr_auto.get_backend_info()
    print(f"Active backend: {info['active_backend']}")
    print(f"Device: {info['device']}")
    print(f"Available backends: {list(info['available_backends'].keys())}")

    for backend in ["whisper", "nemo", "wav2vec2"]:
        print(f"\nTesting {backend}")
        print("-" * 60)
        try:
            asr = ASRService(backend=backend, model_name="tiny")
            backend_info = asr.get_backend_info()
            if backend_info["available_backends"].get(backend, False):
                print(f"{backend} is available")
                print(f"Device: {backend_info['device']}")
            else:
                print(f"{backend} is not installed")
                print(f"Install with: pip install {get_install_command(backend)}")
        except Exception as exc:
            print(f"{backend} failed: {exc}")


def run_transcription_demo(audio_path: str) -> None:
    print(f"\nTranscription demo: {audio_path}")
    print("=" * 60)

    audio_file = Path(audio_path)
    if not audio_file.exists():
        print(f"Audio file not found: {audio_file}")
        return

    for backend in ["auto", "whisper", "nemo", "wav2vec2"]:
        try:
            print(f"\nTesting {backend}")
            print("-" * 40)
            asr = ASRService(backend=backend, model_name="tiny")
            result = asr.transcribe(str(audio_file))
            print(f"Backend used: {result['backend']}")
            print(f"Transcription: {result['text']}")
            print(f"Language: {result.get('language', 'unknown')}")
        except Exception as exc:
            print(f"{backend} skipped: {exc}")


if __name__ == "__main__":
    run_backend_demo()
    if len(sys.argv) > 1:
        run_transcription_demo(sys.argv[1])
    else:
        print("\nTo test transcription, run:")
        print(f"python {Path(__file__).name} path/to/audio.wav")
