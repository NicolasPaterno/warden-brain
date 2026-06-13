from fastapi import Request

from app.services.chat_service import ChatService


def get_chat_service(request: Request) -> ChatService:
    """Returns the singleton ChatService built once in main.py's lifespan.

    No @lru_cache here: the instance already lives on app.state for the app's
    whole life. FastAPI injects the Starlette `request`, and `request.app` is
    the FastAPI app — so we just read what the lifespan stored.
    """
    return request.app.state.chat_service
