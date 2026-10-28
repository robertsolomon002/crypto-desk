"""FastAPI app. Its OpenAPI schema is the contract for the generated frontend client."""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from desk import __version__
from desk.api.routes import health
from desk.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Crypto Desk API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-LLM-Key"],
    )
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()


def write_openapi(path: Path) -> None:
    """Write the OpenAPI schema with stable formatting so CI can diff it."""
    schema = app.openapi()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
