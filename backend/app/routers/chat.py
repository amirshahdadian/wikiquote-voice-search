"""Chat endpoints for text interactions."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_backend_state
from ..schemas import ChatQueryRequest, ChatQueryResponse
from ..state import BackendState

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/query", response_model=ChatQueryResponse)
def chat_query(
    request: ChatQueryRequest,
    state: BackendState = Depends(get_backend_state),
) -> ChatQueryResponse:
    payload = state.process_chat_query(
        message=request.message,
        conversation_id=request.conversation_id,
        selected_user_id=request.selected_user_id,
    )
    return ChatQueryResponse(**payload)
