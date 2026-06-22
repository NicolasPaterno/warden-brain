from datetime import datetime

import httpx

from app.domain.errors import UpstreamError
from app.domain.reading import SensorReading


class GatewayClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._http = http

    async def get_readings(
        self, token: str, room: str, sensor_type: str, start: datetime, end: datetime
            ) -> list[SensorReading]:
        try:
            response = await self._http.get(
                f"{self._base_url}/api/readings",
                params={
                    "room": room,
                    "type": sensor_type,
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
        except httpx.HTTPError as err:
            raise UpstreamError(f"gateway readings request failed: {err}") from err
        return [SensorReading(**reading) for reading in response.json()]

    async def list_rooms(self, token: str) -> list[str]:
        # The gateway scopes rooms to the tenant carried inside `token` (the
        # exchanged on-behalf-of token), so this returns only the logged-in
        # user's rooms — there is no tenant parameter to pass.
        try:
            response = await self._http.get(
                f"{self._base_url}/api/rooms",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
        except httpx.HTTPError as err:
            raise UpstreamError(f"gateway rooms request failed: {err}") from err
        return response.json()
