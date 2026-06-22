from datetime import timedelta

import pytest

from app.domain.chat import ChatAnswer, ChatRequest
from app.domain.errors import UpstreamError
from app.domain.llm import LlmReply, ToolCall
from app.services.chat_service import ChatService
from tests.conftest import FakeAuthClient, FakeGatewayClient, FakeLlmClient


async def test_direct_answer_skips_tools():
    """LLM answers without a tool call -> the brain still exchanges the token and
    lists rooms up front (needed to build the tool's room enum before turn 0), but
    never fetches readings."""
    llm = FakeLlmClient(replies=[LlmReply(content="Hi there")])
    auth = FakeAuthClient()
    gateway = FakeGatewayClient(rooms=["bedroom"])
    service = ChatService(llm, auth, gateway)

    out = await service.answer(ChatRequest(user_message="hello"), user_token="u")

    assert out == ChatAnswer(answer="Hi there")
    assert len(llm.calls) == 1
    assert auth.calls == [("u", "warden-gateway")]
    assert gateway.rooms_calls == ["exchanged-token"]
    assert gateway.calls == []


async def test_tool_call_grounds_answer_in_gateway(sample_readings):
    """LLM requests get_readings -> brain exchanges the token, queries the
    gateway, feeds the summary back, and the LLM's next reply is returned."""
    tool_reply = LlmReply(
        tool_calls=[
            ToolCall(
                name="get_readings",
                arguments={"room": "bedroom", "type": "temperature", "period": "last_24h"},
            )
        ]
    )
    final_reply = LlmReply(content="The bedroom is around 20C.")
    llm = FakeLlmClient(replies=[tool_reply, final_reply])
    auth = FakeAuthClient(token="gw-token")
    gateway = FakeGatewayClient(readings=sample_readings)
    service = ChatService(llm, auth, gateway)

    out = await service.answer(
        ChatRequest(user_message="how's the bedroom?"), user_token="user-token"
    )

    assert out.answer == "The bedroom is around 20C."
    # Exchanged the USER's token for a warden-gateway audience token.
    assert auth.calls == [("user-token", "warden-gateway")]
    # Gateway queried with the exchanged token and the tool's arguments.
    assert gateway.calls[0]["token"] == "gw-token"
    assert gateway.calls[0]["room"] == "bedroom"
    assert gateway.calls[0]["type"] == "temperature"
    # The second LLM turn was fed the tool result.
    second_turn_messages = llm.calls[1]["messages"]
    assert any(m.get("role") == "tool" for m in second_turn_messages)


async def test_room_enum_is_grounded_in_tenant_rooms():
    """The get_readings tool handed to the LLM constrains `room` to the tenant's
    real rooms. Inspect the tool via `llm.calls[0]["tools"][0]` and assert on
    function.parameters.properties.room.enum."""
    llm = FakeLlmClient(replies=[LlmReply(content="ok")])
    gateway = FakeGatewayClient(rooms=["bedroom", "kitchen"])
    service = ChatService(llm, FakeAuthClient(), gateway)

    await service.answer(ChatRequest(user_message="hi"), user_token="u")

    room_schema = llm.calls[0]["tools"][0]["function"]["parameters"]["properties"]["room"]
    assert room_schema["enum"] == ["bedroom", "kitchen"]


async def test_room_enum_falls_back_to_free_string_when_no_rooms():
    """When the gateway returns no rooms, `room` carries no enum (free string)."""
    llm = FakeLlmClient(replies=[LlmReply(content="ok")])
    gateway = FakeGatewayClient(rooms=[])
    service = ChatService(llm, FakeAuthClient(), gateway)

    await service.answer(ChatRequest(user_message="hi"), user_token="u")

    room_schema = llm.calls[0]["tools"][0]["function"]["parameters"]["properties"]["room"]
    assert "enum" not in room_schema
    assert room_schema["type"] == "string"


async def test_direct_answer_with_none_content_uses_fallback():
    """A local model can answer with no tool call AND no text -> we must not
    crash ChatAnswer's str contract."""
    llm = FakeLlmClient(replies=[LlmReply(content=None)])
    service = ChatService(llm, FakeAuthClient(), FakeGatewayClient())

    out = await service.answer(ChatRequest(user_message="hi"), user_token="u")

    assert isinstance(out.answer, str)
    assert out.answer != ""


async def test_assistant_tool_call_is_echoed_before_tool_result(sample_readings):
    """The assistant(tool_calls) message must be pushed back into history before
    the tool(result), so the model sees the pair the protocol expects."""
    tool_reply = LlmReply(
        tool_calls=[ToolCall(name="get_readings", arguments={"room": "bedroom", "type": "temperature"})]
    )
    llm = FakeLlmClient(replies=[tool_reply, LlmReply(content="done")])
    service = ChatService(llm, FakeAuthClient(), FakeGatewayClient(readings=sample_readings))

    await service.answer(ChatRequest(user_message="how's the bedroom?"), user_token="u")

    second_turn = llm.calls[1]["messages"]
    roles = [m["role"] for m in second_turn]
    assistant_idx = roles.index("assistant")
    tool_idx = roles.index("tool")
    assert assistant_idx < tool_idx
    assert second_turn[assistant_idx]["tool_calls"][0]["function"]["name"] == "get_readings"


async def test_gateway_failure_propagates_as_upstream_error(sample_readings):
    """An upstream failure surfaces as a domain UpstreamError (which main.py maps
    to 503) — never a raw httpx exception leaking through the service."""

    class FailingGateway:
        async def list_rooms(self, *args, **kwargs):
            return []

        async def get_readings(self, *args, **kwargs):
            raise UpstreamError("gateway down")

    tool_reply = LlmReply(
        tool_calls=[ToolCall(name="get_readings", arguments={"room": "bedroom", "type": "temperature"})]
    )
    llm = FakeLlmClient(replies=[tool_reply])
    service = ChatService(llm, FakeAuthClient(), FailingGateway())

    with pytest.raises(UpstreamError):
        await service.answer(ChatRequest(user_message="how's the bedroom?"), user_token="u")


async def test_loop_exhausts_returns_fallback():
    """If the LLM keeps calling tools forever, the 4-turn loop ends with a
    fallback answer instead of looping unbounded."""
    tool_reply = LlmReply(
        tool_calls=[ToolCall(name="get_readings", arguments={"room": "bedroom", "type": "temperature"})]
    )
    llm = FakeLlmClient(replies=[tool_reply] * 4)
    service = ChatService(llm, FakeAuthClient(), FakeGatewayClient(readings=[]))

    out = await service.answer(ChatRequest(user_message="x"), user_token="u")

    assert "not able" in out.answer.lower()
    assert len(llm.calls) == 4


def test_summarize_empty_readings():
    assert ChatService._summarize_readings([]) == "No readings for that period."


def test_summarize_uses_latest_as_current(sample_readings):
    text = ChatService._summarize_readings(sample_readings)
    # "current" = reading with the max timestamp (21.0 at hour 5).
    assert "Current: 21.00C" in text
    assert "min 19.00" in text
    assert "max 21.00" in text
    assert "3 readings" in text


@pytest.mark.parametrize(
    "period,expected",
    [
        ("last_hour", timedelta(hours=1)),
        ("last_24h", timedelta(hours=24)),
        ("last_7d", timedelta(days=7)),
        ("nonsense", timedelta(hours=24)),  # unknown -> 24h default
    ],
)
def test_period_to_delta(period, expected):
    assert ChatService._period_to_delta(period) == expected
