import logging
from datetime import datetime, timedelta, timezone

from app.clients.auth_client import AuthClient
from app.clients.gateway_client import GatewayClient
from app.clients.llm_client import LlmClient
from app.domain.chat import ChatAnswer, ChatRequest
from app.domain.reading import SensorReading

logger = logging.getLogger(__name__)

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
                "period": {
                    "type": "string",
                    "enum": ["last_hour", "last_24h", "last_7d"],
                    "description": (
                        "How far back to look. Use 'last_hour' for current/now "
                        "conditions, 'last_24h' for today or last night, 'last_7d' for "
                        "the past week. Defaults to 'last_24h' if the user gives no time."
                    ),
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
        logger.info("chat start: question=%r", request.user_message)

        for turn in range(4):
            logger.debug("turn %d: calling llm with %d messages", turn, len(messages))
            reply = await self.llm.chat(messages, tools=[GET_READINGS_TOOL])

            if not reply.tool_calls:
                logger.info("turn %d: llm answered directly (no tool call)", turn)
                logger.debug("final answer: %r", reply.content)
                return ChatAnswer(answer=reply.content)

            logger.info("turn %d: llm requested %d tool call(s)", turn, len(reply.tool_calls))
            for call in reply.tool_calls:
                logger.info("tool call: name=%s arguments=%s", call.name, call.arguments)
                gw_token = await self.auth.exchange(user_token, "warden-gateway")

                period = call.arguments.get("period", "last_24h")
                end = datetime.now(timezone.utc)
                start = end - self._period_to_delta(period)

                readings = await self.gateway.get_readings(
                    token=gw_token,
                    room=call.arguments["room"],
                    sensor_type=call.arguments["type"],
                    start=start,
                    end=end,
                )
                logger.info(
                    "gateway returned %d readings (room=%s type=%s period=%s)",
                    len(readings), call.arguments.get("room"), call.arguments.get("type"), period,
                )
                logger.debug("readings sample: %s", readings[:3])

                text = self._summarize_readings(readings)
                messages.append({"role": "tool", "tool_name": call.name, "content": text})

        logger.warning("tool loop exhausted (4 turns) without a final answer")
        return ChatAnswer(answer="I was not able find any response based the available data")

    @staticmethod
    def _summarize_readings(readings: list[SensorReading]) -> str:
        if not readings:
            return "No readings for that period."

        values = [r.value for r in readings]
        current = max(readings, key=lambda r: r.timestamp)
        min_value = min(values)
        max_value = max(values)
        avg_value = sum(values) / len(values)

        return (
            f"Current: {current.value:.2f}{current.unit}\n"
            f"Window: min {min_value:.2f}, max {max_value:.2f}, "
            f"avg {avg_value:.2f} ({len(readings)} readings)"
        )

    @staticmethod
    def _period_to_delta(period: str) -> timedelta:
        map_period = {
            "last_hour": timedelta(hours=1),
            "last_24h": timedelta(hours=24),
            "last_7d": timedelta(days=7),
        }
        return map_period.get(period, timedelta(hours=24))