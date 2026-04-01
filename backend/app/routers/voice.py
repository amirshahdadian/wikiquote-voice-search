"""Voice and TTS endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..deps import get_backend_state
from ..schemas import TTSPreviewRequest, TTSPreviewResponse, VoiceQueryResponse
from ..state import BackendState

router = APIRouter(prefix="/api", tags=["voice"])


@router.post("/voice/query", response_model=VoiceQueryResponse)
async def voice_query(
    audio: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    selected_user_id: str | None = Form(default=None),
    state: BackendState = Depends(get_backend_state),
) -> VoiceQueryResponse:
    payload = state.process_voice_query(
        audio_bytes=await audio.read(),
        filename=audio.filename or "voice.wav",
        conversation_id=conversation_id,
        selected_user_id=selected_user_id,
    )
    return VoiceQueryResponse(**payload)


@router.post("/tts/preview", response_model=TTSPreviewResponse)
def tts_preview(
    request: TTSPreviewRequest,
    state: BackendState = Depends(get_backend_state),
) -> TTSPreviewResponse:
    payload = state.create_tts_preview(
        text=request.text,
        user_id=request.user_id,
        preferences=request.preferences.model_dump() if request.preferences else None,
    )
    return TTSPreviewResponse(**payload)
