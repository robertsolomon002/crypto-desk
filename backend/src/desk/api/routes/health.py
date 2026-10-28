"""`/api/health`: liveness check. Does not touch the database, so it answers on a cold start."""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from desk import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    time_utc: datetime


@router.get("/health", response_model=HealthResponse, operation_id="getHealth")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, time_utc=datetime.now(UTC))
