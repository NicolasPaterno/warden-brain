import ollama
from app.domain.errors import LlmError


class LlmClient:
    def __init__(self, host: str, model: str) -> None:
        self._client = ollama.AsyncClient(host=host)
        self._model = model

    async def generate(self, prompt: str) -> str:
        try:
            response = await self._client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
        )
        except (ollama.ResponseError, ConnectionError) as err:
            raise LlmError("Ollama failed to generate Response") from err
        return response.message.content
