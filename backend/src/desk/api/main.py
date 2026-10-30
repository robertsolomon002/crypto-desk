"""FastAPI app. Its OpenAPI schema is the contract for the generated frontend client."""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from desk import __version__
from desk.api.middleware import ETag, LlmKeyRedaction
from desk.api.routes import (
    admin,
    calendar,
    coins,
    cycles,
    data,
    health,
    indicators,
    macro,
    news,
    ohlcv,
    onchain,
    overview,
    stats,
)
from desk.config import get_settings

ROUTERS = [health, coins, overview, ohlcv, indicators, cycles, stats, onchain, macro, news,
           calendar, data, admin]  # fmt: skip


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Crypto Desk API", version=__version__)
    # Added inner to outer: the key is stripped before CORS, gzip or any route sees the request,
    # and ETags are computed on the uncompressed body.
    app.add_middleware(ETag)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-LLM-Key", "If-None-Match"],
        expose_headers=["ETag", "Retry-After", "Content-Disposition"],
    )
    app.add_middleware(LlmKeyRedaction)
    for module in ROUTERS:
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()


def write_openapi(path: Path) -> None:
    """Write the OpenAPI schema with stable formatting so CI can diff it."""
    schema = app.openapi()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
