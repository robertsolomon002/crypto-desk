"""`/api/stats` routes: seasonality, return distribution, drawdowns, volatility, correlation."""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from desk.api.common import run_analytics
from desk.api.deps import AsOfDep, SessionDep, require_role
from desk.api.schemas import AnalyticsData, Envelope

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(require_role("member"))])

AnalyticsEnvelope = Envelope[AnalyticsData]
SEASONALITY = {
    "monthly": "seasonality_monthly",
    "weekly": "seasonality_weekly",
    "dow": "seasonality_dow",
}


@router.get(
    "/{coin}/seasonality/{period}", response_model=AnalyticsEnvelope, operation_id="getSeasonality"
)
def seasonality(
    coin: str, period: Literal["monthly", "weekly", "dow"], session: SessionDep, as_of: AsOfDep
) -> AnalyticsEnvelope:
    """Monthly (year x month), ISO-week or day-of-week returns."""
    return run_analytics(session, SEASONALITY[period], coin, as_of)


@router.get(
    "/{coin}/distribution", response_model=AnalyticsEnvelope, operation_id="getReturnDistribution"
)
def distribution(
    coin: str, session: SessionDep, as_of: AsOfDep, horizon: Literal["1d", "1w", "30d"] = "1w"
) -> AnalyticsEnvelope:
    """Return histogram with the latest period's percentile."""
    return run_analytics(session, "return_distribution", coin, as_of, horizon=horizon)


@router.get("/{coin}/drawdowns", response_model=AnalyticsEnvelope, operation_id="getDrawdowns")
def drawdowns(
    coin: str, session: SessionDep, as_of: AsOfDep, start: dt.date | None = None
) -> AnalyticsEnvelope:
    """Drawdown from the running ATH close, per day."""
    return run_analytics(session, "drawdowns", coin, as_of, start)


@router.get(
    "/{coin}/drawdown-episodes",
    response_model=AnalyticsEnvelope,
    operation_id="getDrawdownEpisodes",
)
def drawdown_episodes(
    coin: str,
    session: SessionDep,
    as_of: AsOfDep,
    top_n: Annotated[int, Query(ge=1, le=50)] = 10,
) -> AnalyticsEnvelope:
    """Deepest peak-to-trough episodes."""
    return run_analytics(session, "drawdown_episodes", coin, as_of, top_n=top_n)


@router.get("/{coin}/volatility", response_model=AnalyticsEnvelope, operation_id="getVolatility")
def volatility(
    coin: str, session: SessionDep, as_of: AsOfDep, start: dt.date | None = None
) -> AnalyticsEnvelope:
    """Annualized 30 and 90 day realized volatility."""
    return run_analytics(session, "rolling_volatility", coin, as_of, start)


@router.get("/{coin}/correlation", response_model=AnalyticsEnvelope, operation_id="getCorrelation")
def correlation(
    coin: str,
    session: SessionDep,
    as_of: AsOfDep,
    window: Annotated[int, Query(ge=10, le=365)] = 90,
    start: dt.date | None = None,
) -> AnalyticsEnvelope:
    """Rolling correlation of daily log returns with the other active coins."""
    return run_analytics(session, "rolling_correlation", coin, as_of, start, window=window)
