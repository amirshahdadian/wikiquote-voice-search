"""Generated audio file serving endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.app.api.dependencies import get_voice_service
from backend.app.services import VoiceService

router = APIRouter(prefix="/api/audio", tags=["audio"])


@router.get("/{audio_id}")
def get_generated_audio(
    audio_id: str,
    voice_service: VoiceService = Depends(get_voice_service),
) -> FileResponse:
    audio_path = voice_service.resolve_audio_path(audio_id)
    if audio_path is None:
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path=audio_path, filename=audio_path.name)
