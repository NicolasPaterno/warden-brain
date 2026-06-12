import ollama


class LlmClient:
    def __init__(self, host: str, model: str) -> None:
        self._client = ollama.AsyncClient(host=host)
        self._model = model

    async def generate(self, prompt: str) -> str:
        response = await self._client.chat(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.message.content
