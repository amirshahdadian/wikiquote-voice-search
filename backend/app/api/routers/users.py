"""User profile and speaker enrollment endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.app.api.dependencies import get_user_service
from backend.app.api.schemas import UserPreferences, UserProfile
from backend.app.services import UserService

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserProfile])
def list_users(user_service: UserService = Depends(get_user_service)) -> list[UserProfile]:
    return [UserProfile(**user) for user in user_service.list_users()]


@router.get("/{user_id}", response_model=UserProfile)
def get_user(user_id: str, user_service: UserService = Depends(get_user_service)) -> UserProfile:
    user = user_service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfile(**user)


@router.post("/register", response_model=UserProfile)
async def register_user(
    display_name: str = Form(...),
    group_identifier: str | None = Form(default=None),
    pitch_scale: float = Form(default=1.0),
    speaking_rate: float = Form(default=1.0),
    energy_scale: float = Form(default=1.0),
    audio_samples: list[UploadFile] = File(...),
    user_service: UserService = Depends(get_user_service),
) -> UserProfile:
    if len(audio_samples) < 3:
        raise HTTPException(status_code=400, detail="At least 3 audio samples are required")

    preferences = UserPreferences(
        pitch_scale=pitch_scale,
        speaking_rate=speaking_rate,
        energy_scale=energy_scale,
    ).model_dump()
    uploads = [(sample.filename or "sample.wav", await sample.read()) for sample in audio_samples]

    try:
        user = user_service.register_user(display_name, group_identifier, preferences, uploads)
        return UserProfile(**user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{user_id}/preferences", response_model=UserProfile)
def update_preferences(
    user_id: str,
    preferences: UserPreferences,
    user_service: UserService = Depends(get_user_service),
) -> UserProfile:
    try:
        user = user_service.update_user_preferences(user_id, preferences.model_dump())
        return UserProfile(**user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/re-enroll", response_model=UserProfile)
async def re_enroll_user(
    user_id: str,
    audio_samples: list[UploadFile] = File(...),
    user_service: UserService = Depends(get_user_service),
) -> UserProfile:
    if len(audio_samples) < 3:
        raise HTTPException(status_code=400, detail="At least 3 audio samples are required")

    uploads = [(sample.filename or "sample.wav", await sample.read()) for sample in audio_samples]
    try:
        user = user_service.re_enroll_user(user_id, uploads)
        return UserProfile(**user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, user_service: UserService = Depends(get_user_service)) -> None:
    try:
        user_service.delete_user(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
