"""FastAPI dependencies for the canonical backend container."""
from __future__ import annotations

from fastapi import Depends, Request

from backend.app.container import AppContainer
from backend.app.services import ConversationService, QuoteSearchService, UserService, VoiceService


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_quote_search_service(container: AppContainer = Depends(get_container)) -> QuoteSearchService:
    return container.quote_search


def get_user_service(container: AppContainer = Depends(get_container)) -> UserService:
    return container.users


def get_voice_service(container: AppContainer = Depends(get_container)) -> VoiceService:
    return container.voice


def get_conversation_service(container: AppContainer = Depends(get_container)) -> ConversationService:
    return container.conversation
