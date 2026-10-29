"""`/api/indicators`, `/api/levels`, `/api/pivots` and `/api/regime` routes."""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from desk.analytics._frames import to_jsonable
from desk.analytics.indicators import IndicatorRequest, custom
from desk.api.common import ANALYTICS_SOURCE, candle_sources, get_coin, run_analytics, trim_start
from desk.api.deps import AsOfDep, SessionDep, require_role
from desk.api.schemas import AnalyticsData, Envelope, Source
from desk.data import market

router = APIRouter(tags=["indicators"], dependencies=[Depends(require_role("member"))])

AnalyticsEnvelope = Envelope[AnalyticsData]
INTS = r"^\d{1,3}(,\d{1,3}){0,5}$"


def _ints(raw: str | None) -> tuple[int, ...]:
    return tuple(int(x) for x in raw.split(",")) if raw else ()


@router.get("/indicators/{coin}", response_model=AnalyticsEnvelope, operation_id="getIndicators")
def get_indicators(
    coin: str,
    session: SessionDep,
    as_of: AsOfDep,
    sma: Annotated[str | None, Query(pattern=INTS, description="e.g. 20,50,200")] = None,
    ema: Annotated[str | None, Query(pattern=INTS)] = None,
    bb: Annotated[str | None, Query(pattern=r"^\d{1,3}:\d+(\.\d+)?$", description="n:k")] = None,
    rsi: Annotated[int | None, Query(ge=2, le=100)] = None,
    macd: Annotated[
        str | None, Query(pattern=r"^\d{1,3}:\d{1,3}:\d{1,3}$", description="fast:slow:signal")
    ] = None,
    vol: Annotated[str | None, Query(pattern=INTS)] = None,
    band: bool = False,
    start: dt.date | None = None,
) -> AnalyticsEnvelope:
    """Selectable indicators with parameters. Every value at day t uses closes up to t only."""
    symbol = get_coin(session, coin).symbol
    bb_parts = bb.split(":") if bb else None
    macd_parts = tuple(int(x) for x in macd.split(":")) if macd else None
    req = IndicatorRequest(
        sma=_ints(sma),
        ema=_ints(ema),
        bollinger=(int(bb_parts[0]), float(bb_parts[1])) if bb_parts else None,
        rsi=rsi,
        macd=macd_parts,  # type: ignore[arg-type]  # the pattern guarantees three parts
        vol=_ints(vol),
        band=band,
    )
    try:
        req.validate()
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    last_date, sources = candle_sources(session, symbol, as_of)
    if last_date is None:
        raise HTTPException(404, f"no data for {symbol} up to {as_of}")
    frame = custom(market.load_daily(session, symbol, as_of), req, as_of)
    params = {k: v for k, v in req.__dict__.items() if v not in ((), None, False)}
    data = AnalyticsData(
        name="indicators",
        coin=symbol,
        params=params,
        cached=False,
        result=trim_start(to_jsonable(frame), start),
    )
    sources.append(Source(name=ANALYTICS_SOURCE, detail="indicators.custom"))
    return Envelope(as_of=last_date, sources=sources, data=data)


@router.get("/levels/{coin}", response_model=AnalyticsEnvelope, operation_id="getLevels")
def get_levels(coin: str, session: SessionDep, as_of: AsOfDep) -> AnalyticsEnvelope:
    """Key levels (previous week high/low, 20W SMA, 50D/200D SMA, ATH, swings) and distances."""
    return run_analytics(session, "levels", coin, as_of)


@router.get("/pivots/{coin}", response_model=AnalyticsEnvelope, operation_id="getPivots")
def get_pivots(
    coin: str,
    session: SessionDep,
    as_of: AsOfDep,
    timeframe: Literal["1d", "1w"] = "1d",
    start: dt.date | None = None,
) -> AnalyticsEnvelope:
    """Zigzag swing pivots with a volatility-scaled threshold (D35)."""
    return run_analytics(session, "pivots", coin, as_of, start, timeframe=timeframe)


@router.get("/regime/{coin}", response_model=AnalyticsEnvelope, operation_id="getRegime")
def get_regime(coin: str, session: SessionDep, as_of: AsOfDep) -> AnalyticsEnvelope:
    """Regime label (frozen D34 rules) with its inputs and history."""
    return run_analytics(session, "regime", coin, as_of)
