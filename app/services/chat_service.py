from app.clients.llm_client import LlmClient
from app.domain.chat import ChatAnswer, ChatRequest


class ChatService:
    def __init__(self, llm_client: LlmClient) -> None:
        self.llm = llm_client

    async def answer(self, request: ChatRequest) -> ChatAnswer:
        prompt = request.user_message
        answer_text = await self.llm.generate(prompt)
        return ChatAnswer(answer=answer_text)
