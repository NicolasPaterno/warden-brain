from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_chat_service
from app.domain.chat import ChatAnswer, ChatRequest
from app.services.chat_service import ChatService

router = APIRouter(tags=["chat"])
bearer = HTTPBearer()


@router.post("/chat", response_model=ChatAnswer)
async def chat(
    request: ChatRequest,
    # TODO (see TODO.md): Phase 4 — HTTPBearer only *extracts* the token here; it does not
    # verify it. Phase 4 must verify the user JWT against auth's JWKS (signature/iss/aud/exp)
    # before using it, and register the brain in auth's AUDIENCE list.
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    service: ChatService = Depends(get_chat_service),
) -> ChatAnswer:
    return await service.answer(request, user_token=credentials.credentials)
