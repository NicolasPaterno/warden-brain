from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes_health import router as health_router
from app.api.routes_chat import router as chat_router
from app.domain.errors import LlmError


app = FastAPI()

@app.exception_handler(LlmError)  # + o tradutor
async def handle_llm_error(request: Request, exc: LlmError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "The assistant is temporarily unavailable."},
    )

app.include_router(health_router)
app.include_router(chat_router)