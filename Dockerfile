# syntax=docker/dockerfile:1

# --- builder: resolve + install deps into a .venv with uv ---
FROM python:3.13-slim AS builder

# Bring in the uv binary (pinned for reproducible builds).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# Compile .pyc on install (faster cold start); copy instead of hardlink across mounts.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first, WITHOUT the app, so this layer is cached and only
# re-runs when pyproject.toml / uv.lock change — not on every source edit.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Now add the app and install it. --no-dev keeps pytest/ruff out of the image.
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# --- runtime: slim image with only the venv + app, run as non-root ---
FROM python:3.13-slim

RUN useradd --create-home --uid 1000 brain
WORKDIR /app

COPY --from=builder --chown=brain:brain /app /app

# Put the venv on PATH so `uvicorn` resolves without `uv run`.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER brain
EXPOSE 8000

# Liveness probe for orchestrators that read Docker HEALTHCHECK (no curl in slim).
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
