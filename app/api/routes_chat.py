from fastapi import APIRouter, Depends

from app.api.deps import get_chat_service, require_user
from app.domain.chat import ChatAnswer, ChatRequest
from app.domain.principal import Principal
from app.services.chat_service import ChatService

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatAnswer)
async def chat(
    request: ChatRequest,
    principal: Principal = Depends(require_user),
    service: ChatService = Depends(get_chat_service),
) -> ChatAnswer:
    return await service.answer(request, user_token=principal.token)
