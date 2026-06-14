"""Shared fakes and fixtures.

The fakes are plain classes implementing the SAME method signatures as the real
clients — no network, no Ollama, no real JWTs. This is the Python equivalent of
the Go services injecting a fake ReadingRepository: ChatService depends on the
methods, not on the concrete httpx/ollama classes, so we swap them freely.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.chat import ChatAnswer
from app.domain.llm import LlmReply
from app.domain.reading import SensorReading
from app.main import app as fastapi_app


class FakeLlmClient:
    """Stands in for LlmClient. Returns scripted replies in order; `alive`
    drives the readiness ping."""

    def __init__(self, replies: list[LlmReply] | None = None, alive: bool = True) -> None:
        self._replies = list(replies or [])
        self.alive = alive
        self.calls: list[dict] = []

    async def chat(self, messages: list[dict], tools: list[dict]) -> LlmReply:
        # Snapshot the messages so a later mutation of the list doesn't change
        # what we recorded for this call.
        self.calls.append({"messages": [m.copy() for m in messages], "tools": tools})
        if self._replies:
            return self._replies.pop(0)
        return LlmReply(content="(no scripted reply left)")

    async def ping(self) -> bool:
        return self.alive


class FakeAuthClient:
    """Stands in for AuthClient. Returns a fixed exchanged token and records the
    (subject_token, audience) pairs it was asked to exchange."""

    def __init__(self, token: str = "exchanged-token") -> None:
        self._token = token
        self.calls: list[tuple[str, str]] = []

    async def exchange(self, subject_token: str, audience: str) -> str:
        self.calls.append((subject_token, audience))
        return self._token


class FakeGatewayClient:
    """Stands in for GatewayClient. Returns canned readings and records the
    query parameters of each call."""

    def __init__(self, readings: list[SensorReading] | None = None) -> None:
        self._readings = list(readings or [])
        self.calls: list[dict] = []

    async def get_readings(self, token, room, sensor_type, start, end) -> list[SensorReading]:
        self.calls.append(
            {"token": token, "room": room, "type": sensor_type, "start": start, "end": end}
        )
        return list(self._readings)


class FakeJwtVerifier:
    """Stands in for JwtVerifier. Returns canned claims, or raises the given
    error (use app.domain.errors.InvalidTokenError to simulate a bad token)."""

    def __init__(self, claims: dict | None = None, error: Exception | None = None) -> None:
        self._claims = claims or {}
        self._error = error
        self.calls: list[str] = []

    def verify(self, token: str) -> dict:
        self.calls.append(token)
        if self._error is not None:
            raise self._error
        return self._claims


class FakeChatService:
    """Stands in for ChatService at the route layer, so /chat tests don't touch
    the LLM/gateway. Records the request + forwarded user token."""

    def __init__(self, answer: str = "canned answer") -> None:
        self._answer = answer
        self.calls: list[dict] = []

    async def answer(self, request, user_token: str) -> ChatAnswer:
        self.calls.append({"request": request, "user_token": user_token})
        return ChatAnswer(answer=self._answer)


@pytest.fixture
def sample_readings() -> list[SensorReading]:
    def reading(value: float, hour: int) -> SensorReading:
        return SensorReading(
            tenant_id="t1",
            sensor_id="s1",
            room="bedroom",
            type="temperature",
            value=value,
            unit="C",
            timestamp=datetime(2026, 6, 13, hour, 0, tzinfo=timezone.utc),
        )

    # Out of timestamp order on purpose, so "current = latest" is actually tested.
    return [reading(19.0, 1), reading(21.0, 5), reading(20.0, 3)]


@pytest.fixture
def client():
    """TestClient with the lifespan run (singletons built). Tests register
    dependency overrides on `fastapi_app`; we clear them on teardown."""
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()
