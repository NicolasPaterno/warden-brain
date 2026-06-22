import logging
from datetime import datetime, timedelta, timezone

from app.clients.auth_client import AuthClient
from app.clients.gateway_client import GatewayClient
from app.clients.llm_client import LlmClient
from app.domain.chat import ChatAnswer, ChatRequest
from app.domain.errors import UpstreamError
from app.domain.reading import SensorReading

logger = logging.getLogger(__name__)

# Bounds the agent loop: each turn is one LLM round-trip, so this caps how many
# times the model may call a tool before we give up and return a fallback.
MAX_TURNS = 4

def build_get_readings_tool(rooms: list[str]) -> dict:
    """Build the get_readings tool schema, constraining `room` to the rooms that
    actually exist for this user's tenant. A fresh dict is built per call so the
    per-request `enum` never leaks across requests. When `rooms` is empty (e.g.
    the gateway is unreachable), `room` falls back to a free string."""
    room_schema: dict = {"type": "string", "description": "The room to query, e.g. 'bedroom'."}
    if rooms:
        room_schema["enum"] = rooms

    return {
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
                    "room": room_schema,
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

        # Trade the user's token for a gateway-scoped on-behalf-of token ONCE, up
        # front: we need it to fetch the room list BEFORE the LLM's first turn, so
        # the get_readings tool can constrain `room` to rooms that actually exist.
        # The exchanged token carries the user's tenant, so /api/rooms (and later
        # /api/readings) are scoped to THIS user's tenant by the gateway. One
        # exchange for the whole request also avoids spamming auth's rate limiter.
        gw_token = await self.auth.exchange(user_token, "warden-gateway")

        # Ground the tool's `room` enum in the tenant's real rooms. If the gateway
        # is unreachable, degrade to a free-string room instead of failing the chat.
        try:
            rooms = await self.gateway.list_rooms(gw_token)
        except UpstreamError:
            logger.warning("could not list rooms; falling back to free-string room", exc_info=True)
            rooms = []
        logger.info("available rooms for tenant: %s", rooms)

        tool = build_get_readings_tool(rooms)

        for turn in range(MAX_TURNS):
            logger.debug("turn %d: calling llm with %d messages", turn, len(messages))
            reply = await self.llm.chat(messages, tools=[tool])

            if not reply.tool_calls:
                logger.info("turn %d: llm answered directly (no tool call)", turn)
                logger.debug("final answer: %r", reply.content)
                # content is Optional: a local model can answer with no tool call
                # AND no text. Honor ChatAnswer's str contract instead of letting
                # Pydantic raise on None.
                return ChatAnswer(answer=reply.content or "I couldn't produce an answer for that.")

            logger.info("turn %d: llm requested %d tool call(s)", turn, len(reply.tool_calls))
            # Echo the assistant turn that requested the tools back into history
            # BEFORE the results, so the model sees the assistant(tool_calls) ->
            # tool(result) pair the protocol expects (otherwise it tends to repeat
            # the same call and exhaust the loop). A plain dict keeps the ollama
            # Message type out of the service — `messages` is already its dict shape.
            messages.append(
                {
                    "role": "assistant",
                    "content": reply.content or "",
                    "tool_calls": [
                        {"function": {"name": c.name, "arguments": c.arguments}}
                        for c in reply.tool_calls
                    ],
                }
            )
            for call in reply.tool_calls:
                logger.info("tool call: name=%s arguments=%s", call.name, call.arguments)
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

        logger.warning("tool loop exhausted (%d turns) without a final answer", MAX_TURNS)
        return ChatAnswer(answer="I was not able find any response based the available data")

    @staticmethod
    def _summarize_readings(readings: list[SensorReading]) -> str:
        if not readings:
            return "No readings for that period."

        values = [r.value for r in readings]
        current = max(readings, key=lambda r: r.timestamp)
        unit = current.unit
        min_value = min(values)
        max_value = max(values)
        avg_value = sum(values) / len(values)

        return (
            f"Current: {current.value:.2f}{unit}\n"
            f"Window: min {min_value:.2f}{unit}, max {max_value:.2f}{unit}, "
            f"avg {avg_value:.2f}{unit} ({len(readings)} readings)"
        )

    @staticmethod
    def _period_to_delta(period: str) -> timedelta:
        map_period = {
            "last_hour": timedelta(hours=1),
            "last_24h": timedelta(hours=24),
            "last_7d": timedelta(days=7),
        }
        return map_period.get(period, timedelta(hours=24))