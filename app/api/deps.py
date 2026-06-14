from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from app.clients.llm_client import LlmClient
from app.domain.errors import InvalidTokenError
from app.domain.principal import Principal
from app.security.jwt_verifier import JwtVerifier
from app.services.chat_service import ChatService

_bearer_scheme = HTTPBearer(auto_error=False)


def get_llm_client(request: Request) -> LlmClient:
    """Returns the singleton LlmClient built once in main.py's lifespan."""
    return request.app.state.llm_client


def get_chat_service(request: Request) -> ChatService:
    """Returns the singleton ChatService built once in main.py's lifespan.

    No @lru_cache here: the instance already lives on app.state for the app's
    whole life. FastAPI injects the Starlette `request`, and `request.app` is
    the FastAPI app — so we just read what the lifespan stored.
    """
    return request.app.state.chat_service


def get_jwt_verifier(request: Request) -> JwtVerifier:
    """Returns the singleton JwtVerifier built once in main.py's lifespan."""
    return request.app.state.jwt_verifier


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    verifier: JwtVerifier = Depends(get_jwt_verifier),
) -> Principal:
    """Auth guard for protected routes: verify the user's JWT or reject with 401.

    Returns the authenticated Principal so the route can both trust the caller
    and forward the original token to auth's on-behalf-of exchange. Raising here
    short-circuits the request before the handler body ever runs.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        claims = await run_in_threadpool(verifier.verify, token)
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Principal(subject=claims.get("sub", ""), token=token, claims=claims)
