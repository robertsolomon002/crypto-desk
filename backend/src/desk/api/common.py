"""Helpers shared by the read routes: coin lookup, provenance, and the analytics runner.

Analytics routes are thin wrappers over `run_analytics`, which calls the same registry as the
CLI, the cache and desk-mcp (D33). Heavy functions go through `analytics_cache`.
"""

import datetime as dt
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from desk.analytics import cache, registry
from desk.analytics.inputs import load_inputs
from desk.api.schemas import AnalyticsData, Envelope, Source
from desk.models import CandleDaily, Coin

ANALYTICS_SOURCE = "desk.analytics"


def get_coin(session: Session, symbol: str) -> Coin:
    coin = session.get(Coin, symbol.upper())
    if coin is None or not coin.active:
        raise HTTPException(404, f"unknown coin {symbol.upper()!r}")
    return coin


def candle_sources(
    session: Session, coin: str, as_of: dt.date | None
) -> tuple[dt.date | None, list[Source]]:
    """The last candle date (<= as_of) and one Source per candle source with its last date."""
    q = select(CandleDaily.source, func.max(CandleDaily.date)).where(CandleDaily.coin == coin)
    if as_of is not None:
        q = q.where(CandleDaily.date <= as_of)
    rows = session.execute(q.group_by(CandleDaily.source).order_by(func.max(CandleDaily.date)))
    sources = [Source(name=s, detail=f"candles_daily:{coin}", last_date=d) for s, d in rows]
    return (max((s.last_date for s in sources), default=None), sources)  # type: ignore[arg-type]


def trim_start(result: Any, start: dt.date | None) -> Any:
    """Drop records dated before `start` from a date-indexed list result."""
    if start is None or not isinstance(result, list):
        return result
    iso = start.isoformat()
    return [r for r in result if not isinstance(r, dict) or str(r.get("date", iso)) >= iso]


def run_analytics(
    session: Session,
    name: str,
    symbol: str,
    as_of: dt.date | None,
    start: dt.date | None = None,
    **params: Any,
) -> Envelope[AnalyticsData]:
    coin = get_coin(session, symbol).symbol
    spec = registry.get(name)
    resolved = registry.resolve_params(spec, params)
    last_date, sources = candle_sources(session, coin, as_of)
    if last_date is None:
        raise HTTPException(404, f"no data for {coin} up to {as_of}")
    try:
        if spec.heavy:
            result, cached = cache.get_or_compute(session, name, coin, as_of, **resolved)
            session.commit()
        else:
            coins = [coin]
            if spec.needs == "all_coins":
                coins = list(session.scalars(select(Coin.symbol).where(Coin.active)))
            inputs = load_inputs(session, coins, as_of)
            result, cached = registry.run_json(name, inputs, coin, as_of, **resolved), False
    except ValueError as e:
        if "not available" in str(e):
            raise HTTPException(404, str(e)) from None
        raise HTTPException(422, str(e)) from None
    if spec.needs == "onchain":
        sources.append(Source(name="coinmetrics", detail=f"cm:{coin}:*"))
    sources.append(Source(name=ANALYTICS_SOURCE, detail=name))
    data = AnalyticsData(
        name=name, coin=coin, params=resolved, cached=cached, result=trim_start(result, start)
    )
    return Envelope(as_of=last_date, sources=sources, data=data)
