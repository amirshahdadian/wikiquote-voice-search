"""Chat endpoints for text interactions."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_conversation_service
from backend.app.api.schemas import ChatQueryRequest, ChatQueryResponse
from backend.app.services import ConversationService

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/query", response_model=ChatQueryResponse)
def chat_query(
    request: ChatQueryRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ChatQueryResponse:
    payload = conversation_service.process_chat_query(
        message=request.message,
        conversation_id=request.conversation_id,
        selected_user_id=request.selected_user_id,
    )
    return ChatQueryResponse(**payload)
