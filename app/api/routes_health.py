from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_llm_client
from app.clients.llm_client import LlmClient

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    """Liveness: the process is up and the event loop is responsive.

    Deliberately checks nothing external — a liveness probe must not fail just
    because a dependency is down, or the orchestrator would kill a healthy
    process. Dependency health belongs in /ready.
    """
    return {"status": "ok"}


@router.get("/ready")
async def ready(llm: LlmClient = Depends(get_llm_client)) -> dict[str, str]:
    """Readiness: the brain can actually serve a chat request.

    Checks only Ollama, the brain's hard local dependency (no LLM, no answer).
    It deliberately does NOT probe gateway/auth: those are checked per-request
    via the user's token, and gating readiness on downstream services would make
    one service's outage cascade into the whole mesh reporting "not ready".
    """
    if not await llm.ping():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM backend unavailable.",
        )
    return {"status": "ready"}
