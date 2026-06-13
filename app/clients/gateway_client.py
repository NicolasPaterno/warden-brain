from datetime import datetime

import httpx

from app.domain.reading import SensorReading


class GatewayClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._http = http

    async def get_readings(
        self, token: str, room: str, sensor_type: str, start: datetime, end: datetime
            ) -> list[SensorReading]:
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
        return [SensorReading(**reading) for reading in response.json()]
