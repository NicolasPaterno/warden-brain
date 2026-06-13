from datetime import datetime, timedelta, timezone

from app.clients.auth_client import AuthClient
from app.clients.gateway_client import GatewayClient
from app.clients.llm_client import LlmClient
from app.domain.chat import ChatAnswer, ChatRequest

GET_READINGS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_readings",
        "description": (
            "Fetches recent sensor readings for a given room from the home's sensor "
            "system. Call this tool whenever the user asks about the conditions or "
            "environment of the house (temperature, humidity, movement, air quality), "
            "so the answer is grounded in real data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                # TODO (see TODO.md): `room` enum is dynamic — fetch available rooms from the
                # gateway at runtime instead of a free string / hardcoded "bedroom".
                "room": {"type": "string", "description": "The room to query, e.g. 'bedroom'."},
                "type": {
                    "type": "string",
                    "enum": ["temperature", "humidity", "motion", "co2"],
                    "description": "The kind of sensor metric to retrieve.",
                },
            },
            "required": ["room", "type"],
        },
    },
}


class ChatService:
    def __init__(self, llm_client: LlmClient, auth_client: AuthClient, gateway_client: GatewayClient) -> None:
        self.llm = llm_client
        self.auth = auth_client
        self.gateway = gateway_client

    async def answer(self, request: ChatRequest, user_token: str) -> ChatAnswer:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Warden, an assistant for a smart home. You have NO prior "
                    "knowledge about this house. The ONLY way to obtain any sensor "
                    "information (temperature, humidity, motion, CO2) is by calling the "
                    "get_readings tool. For ANY question about the home's conditions you MUST "
                    "call get_readings first. Never answer from general knowledge and never "
                    "suggest external weather services, websites, or apps. After the tool "
                    "returns data, answer based only on it; if it returns no readings, say "
                    "there is no data for that period. Answer in English, concisely."
                ),
            },
            {"role": "user", "content": request.user_message},
        ]

        for _ in range(4):
            reply = await self.llm.chat(messages, tools=[GET_READINGS_TOOL])

            if not reply.tool_calls:
                return ChatAnswer(answer=reply.content)

            for call in reply.tool_calls:
                gw_token = await self.auth.exchange(user_token, "warden-gateway")

                end = datetime.now(timezone.utc)
                start = end - timedelta(hours=1)

                readings = await self.gateway.get_readings(
                    token=gw_token,
                    room=call.arguments["room"],
                    sensor_type=call.arguments["type"],
                    start=start,
                    end=end,
                )

                text = "\n".join(
                    f"{r.timestamp:%H:%M} - {r.value:.1f}{r.unit}" for r in readings[:15]
                )
                messages.append({"role": "tool", "tool_name": call.name, "content": text})

        return ChatAnswer(answer="I was not able find any response based the available data")