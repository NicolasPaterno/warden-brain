from app.api.deps import get_chat_service, get_jwt_verifier, get_llm_client
from app.domain.errors import InvalidTokenError, UpstreamError
from app.main import app as fastapi_app
from tests.conftest import FakeChatService, FakeJwtVerifier, FakeLlmClient

# --- /chat auth guard (Phase 4) ---

def test_chat_without_token_is_401(client):
    resp = client.post("/chat", json={"user_message": "hi"})
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_chat_with_invalid_token_is_401(client):
    fastapi_app.dependency_overrides[get_jwt_verifier] = lambda: FakeJwtVerifier(
        error=InvalidTokenError("bad signature")
    )
    resp = client.post(
        "/chat", json={"user_message": "hi"}, headers={"Authorization": "Bearer nope"}
    )
    assert resp.status_code == 401


def test_chat_with_valid_token_returns_answer(client):
    fastapi_app.dependency_overrides[get_jwt_verifier] = lambda: FakeJwtVerifier(
        claims={"sub": "user-1"}
    )
    fake_service = FakeChatService(answer="The bedroom is 20C.")
    fastapi_app.dependency_overrides[get_chat_service] = lambda: fake_service

    resp = client.post(
        "/chat",
        json={"user_message": "how's the bedroom?"},
        headers={"Authorization": "Bearer good-token"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"answer": "The bedroom is 20C."}
    # The route forwarded the ORIGINAL user token to the service for the exchange.
    assert fake_service.calls[0]["user_token"] == "good-token"


def test_chat_upstream_failure_returns_503(client):
    """A downstream (auth/gateway) outage surfaces as a domain UpstreamError,
    which the app maps to a graceful 503 — not a raw 500."""
    fastapi_app.dependency_overrides[get_jwt_verifier] = lambda: FakeJwtVerifier(
        claims={"sub": "user-1"}
    )

    class FailingService:
        async def answer(self, request, user_token):
            raise UpstreamError("gateway down")

    fastapi_app.dependency_overrides[get_chat_service] = lambda: FailingService()

    resp = client.post(
        "/chat",
        json={"user_message": "how's the bedroom?"},
        headers={"Authorization": "Bearer good-token"},
    )
    assert resp.status_code == 503


# --- health probes (Phase 5) ---

def test_live_is_ok(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_ok_when_llm_reachable(client):
    fastapi_app.dependency_overrides[get_llm_client] = lambda: FakeLlmClient(alive=True)
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


def test_ready_503_when_llm_down(client):
    fastapi_app.dependency_overrides[get_llm_client] = lambda: FakeLlmClient(alive=False)
    resp = client.get("/health/ready")
    assert resp.status_code == 503


def test_metrics_endpoint_exposed(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "http_request" in resp.text
