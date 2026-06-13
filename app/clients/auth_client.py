import httpx


class AuthClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str, http: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http

    async def exchange(self, subject_token: str, audience: str) -> str:
        response = await self._http.post(
            f"{self._base_url}/token/exchange",
            json={
                "client_id":self._client_id,
                "client_secret":self._client_secret,
                "subject_token":subject_token,
                "audience":audience
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]