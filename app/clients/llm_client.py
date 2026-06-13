import ollama
from app.domain.errors import LlmError
from app.domain.llm import LlmReply, ToolCall


class LlmClient:
    def __init__(self, host: str, model: str) -> None:
        self._client = ollama.AsyncClient(host=host)
        self._model = model

    async def chat(self, messages: list[dict], tools: list[dict]) -> LlmReply:
        try:
            response = await self._client.chat(
                model=self._model,
                messages=messages,
                tools=tools,
        )
        except (ollama.ResponseError, ConnectionError) as err:
            raise LlmError("Ollama failed to generate Response") from err

        msg = response.message
        tool_calls = []
        for tc in (msg.tool_calls or []):
            tool_calls.append(ToolCall(name=tc.function.name, arguments=tc.function.arguments))
        return LlmReply(content=msg.content, tool_calls=tool_calls)
