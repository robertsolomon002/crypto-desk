"""`/api/cycles` routes: anchors, overlays by anchor mode, day N, ROI since bottom, YoY."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from desk.api.common import run_analytics
from desk.api.deps import AsOfDep, SessionDep, require_role
from desk.api.schemas import AnalyticsData, Envelope

router = APIRouter(
    prefix="/cycles", tags=["cycles"], dependencies=[Depends(require_role("member"))]
)

AnalyticsEnvelope = Envelope[AnalyticsData]
Mode = Literal["halving", "bottom", "top"]


@router.get("/{coin}/anchors", response_model=AnalyticsEnvelope, operation_id="getCycleAnchors")
def anchors(coin: str, session: SessionDep, as_of: AsOfDep) -> AnalyticsEnvelope:
    """Cycle bottoms, halvings and tops; an anchor is known only once its window ends (D35)."""
    return run_analytics(session, "cycles_anchors", coin, as_of)


@router.get("/{coin}/paths", response_model=AnalyticsEnvelope, operation_id="getCyclePaths")
def paths(
    coin: str,
    session: SessionDep,
    as_of: AsOfDep,
    mode: Mode = "halving",
    max_days: Annotated[int, Query(ge=30, le=2000)] = 1500,
) -> AnalyticsEnvelope:
    """Each cycle as day offsets from its anchor, normalized to the anchor price."""
    return run_analytics(session, "cycles_paths", coin, as_of, mode=mode, max_days=max_days)


@router.get("/{coin}/day-n", response_model=AnalyticsEnvelope, operation_id="getCycleDayN")
def day_n(
    coin: str, session: SessionDep, as_of: AsOfDep, mode: Mode = "halving"
) -> AnalyticsEnvelope:
    """Every past cycle at the current cycle's day N."""
    return run_analytics(session, "cycles_day_n", coin, as_of, mode=mode)


@router.get("/{coin}/roi", response_model=AnalyticsEnvelope, operation_id="getRoiSinceBottom")
def roi(coin: str, session: SessionDep, as_of: AsOfDep) -> AnalyticsEnvelope:
    """Return since each cycle bottom at fixed days and at the current day N."""
    return run_analytics(session, "roi_since_bottom", coin, as_of)


@router.get("/{coin}/yoy", response_model=AnalyticsEnvelope, operation_id="getYoy")
def yoy(coin: str, session: SessionDep, as_of: AsOfDep) -> AnalyticsEnvelope:
    """Each calendar year normalized to its first close."""
    return run_analytics(session, "yoy", coin, as_of)
