from functools import lru_cache

from app.clients.llm_client import LlmClient
from app.config import get_settings
from app.services.chat_service import ChatService


@lru_cache
def get_chat_service() -> ChatService:
    """Builds the ChatService once (and reuses it) — the composition root for /chat.

    @lru_cache makes this a singleton: the LlmClient (and its AsyncClient) is
    created on the first request and reused afterwards, instead of per request.
    """
    settings = get_settings()
    llm_client = LlmClient(host=settings.ollama_host, model=settings.ollama_model)
    return ChatService(llm_client)
