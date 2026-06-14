import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes_chat import router as chat_router
from app.api.routes_health import router as health_router
from app.clients.auth_client import AuthClient
from app.clients.gateway_client import GatewayClient
from app.clients.llm_client import LlmClient
from app.config import get_settings
from app.domain.errors import LlmError, UpstreamError
from app.security.jwt_verifier import JwtVerifier
from app.services.chat_service import ChatService
from app.telemetry import setup_metrics, setup_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    async with httpx.AsyncClient() as http:
        llm = LlmClient(
            host=settings.llm_host,
            model=settings.llm_model
        )
        auth = AuthClient(
            base_url=settings.auth_base_url,
            client_id=settings.brain_client_id,
            client_secret=settings.brain_client_secret,
            http=http,
        )
        gateway = GatewayClient(
            base_url=settings.gateway_base_url,
            http=http
        )

        app.state.llm_client = llm
        app.state.chat_service = ChatService(llm, auth, gateway)
        app.state.jwt_verifier = JwtVerifier(
            jwks_url=settings.jwks_url,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
        yield

app = FastAPI(lifespan=lifespan)

@app.exception_handler(LlmError)
async def handle_llm_error(request: Request, exc: LlmError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "The assistant is temporarily unavailable."},
    )


@app.exception_handler(UpstreamError)
async def handle_upstream_error(request: Request, exc: UpstreamError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "The home data service is temporarily unavailable."},
    )


app.include_router(health_router)
app.include_router(chat_router)

setup_metrics(app)
setup_tracing(app, get_settings())
