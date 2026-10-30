"""`/api/overview`: everything the Overview tab needs in one call (Stage 3.1).

Coin cards come from the `summary` analytics function (so the look-ahead test covers them), and
the freshness strip from the last date of each source. Members see only the daily job's status
and time; its error text stays in `job_runs` (admin-only).
"""

import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from desk.analytics import registry
from desk.analytics.inputs import Inputs
from desk.api.common import ANALYTICS_SOURCE
from desk.api.deps import AsOfDep, SessionDep, require_role
from desk.api.schemas import Envelope, Source
from desk.data import market, sentiment
from desk.data.coins import active_coins
from desk.models import CandleDaily, JobRun, News, SeriesPoint

router = APIRouter(tags=["overview"], dependencies=[Depends(require_role("member"))])


class CoinCard(BaseModel):
    symbol: str
    name: str
    is_watchlist: bool
    date: dt.date | None
    close: float | None
    change_1d: float | None
    change_7d: float | None
    change_30d: float | None
    ath: float | None
    ath_date: dt.date | None
    ath_distance: float | None
    regime: str
    signal: None = None  # v1.3 (Signals)
    mco_bias: None = None  # v1.2 (MCO)


class Freshness(BaseModel):
    source: str  # what the UI shows, e.g. "Prices", "Fear & Greed"
    table: str  # Data tab table for the "View data" link
    last_date: dt.date | None
    max_age_days: int  # older than this (against as_of or today) is stale
    stale: bool


class JobStatus(BaseModel):
    status: str  # running | success | failed
    started_at: dt.datetime
    ended_at: dt.datetime | None


class OverviewData(BaseModel):
    coins: list[CoinCard]
    freshness: list[Freshness]
    daily_job: JobStatus | None  # null when as_of is set (job history isn't as-of data)


# (label, table, series key prefix or None, max age in days). FRED is monthly with release lags
# (D32), so it is only stale after about two months.
_SERIES = [
    ("Fear & Greed", sentiment.KEY, 2),
    ("Dominance", "dominance:", 2),
    ("FRED macro", "fred:", 62),
]


def _series_last(session: Session, key: str, as_of: dt.date | None) -> dt.date | None:
    match = SeriesPoint.key.startswith(key) if key.endswith(":") else SeriesPoint.key == key
    q = select(func.max(SeriesPoint.date)).where(match)
    if as_of is not None:
        q = q.where(SeriesPoint.date <= as_of)
    return session.scalar(q)


def _freshness(session: Session, as_of: dt.date | None) -> list[Freshness]:
    candles = select(func.max(CandleDaily.date))
    news = select(func.max(News.published_at))
    if as_of is not None:
        candles = candles.where(CandleDaily.date <= as_of)
        end = dt.datetime.combine(as_of, dt.time(), dt.UTC) + dt.timedelta(days=1)
        news = news.where(News.published_at < end)
    newest = session.scalar(news)
    found = [
        ("Prices", "candles_daily", session.scalar(candles), 2),
        *[(label, "series", _series_last(session, key, as_of), age)
          for label, key, age in _SERIES],
        ("Headlines", "news", newest.date() if newest else None, 2),
    ]  # fmt: skip
    today = as_of or dt.datetime.now(dt.UTC).date()
    return [
        Freshness(source=label, table=table, last_date=last, max_age_days=age,
                  stale=last is None or (today - last).days > age)
        for label, table, last, age in found
    ]  # fmt: skip


def _daily_job(session: Session) -> JobStatus | None:
    run = session.scalar(
        select(JobRun).where(JobRun.job == "daily").order_by(JobRun.started_at.desc()).limit(1)
    )
    if run is None:
        return None
    return JobStatus(status=run.status, started_at=run.started_at, ended_at=run.ended_at)


@router.get("/overview", response_model=Envelope[OverviewData], operation_id="getOverview")
def get_overview(session: SessionDep, as_of: AsOfDep) -> Envelope[OverviewData]:
    """Coin cards (core first, then the watchlist), source freshness and the daily job status."""
    coins = list(active_coins(session))
    inputs = Inputs({c.symbol: market.load_daily(session, c.symbol, as_of) for c in coins})
    cards = []
    for coin in coins:
        s = registry.run("summary", inputs, coin.symbol, as_of)
        cards.append(CoinCard(symbol=coin.symbol, name=coin.name, is_watchlist=coin.is_watchlist,
                              date=s.date, close=s.close, change_1d=s.change_1d,
                              change_7d=s.change_7d, change_30d=s.change_30d, ath=s.ath,
                              ath_date=s.ath_date, ath_distance=s.ath_distance,
                              regime=s.regime))  # fmt: skip
    freshness = _freshness(session, as_of)
    sources = [Source(name="coinbase", detail="candles_daily", last_date=freshness[0].last_date),
               Source(name=ANALYTICS_SOURCE, detail="summary"),
               Source(name="database", detail="freshness: candles, series, news")]  # fmt: skip
    data = OverviewData(coins=cards, freshness=freshness,
                        daily_job=None if as_of else _daily_job(session))  # fmt: skip
    return Envelope(as_of=freshness[0].last_date, sources=sources, data=data)
