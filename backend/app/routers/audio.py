"""Generated audio file serving endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..deps import get_backend_state
from ..state import BackendState

router = APIRouter(prefix="/api/audio", tags=["audio"])


@router.get("/{audio_id}")
def get_generated_audio(
    audio_id: str,
    state: BackendState = Depends(get_backend_state),
) -> FileResponse:
    audio_path = state.resolve_audio_path(audio_id)
    if audio_path is None:
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path=audio_path, filename=audio_path.name)
