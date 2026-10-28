# Build from the repo root so config/ and prompts/ are included:
#   docker build -f backend/Dockerfile -t crypto-desk-api .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    DESK_ROOT=/app

WORKDIR /app/backend

# Dependencies first, for layer caching
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/ ./
COPY config/ /app/config/
COPY prompts/ /app/prompts/
RUN uv sync --locked --no-dev

RUN useradd --create-home --uid 10001 desk && chown -R desk /app
USER desk

# Cloud Run sets PORT (default 8080)
ENV PORT=8080
CMD ["sh", "-c", "exec /app/backend/.venv/bin/uvicorn desk.api.main:app --host 0.0.0.0 --port ${PORT}"]
