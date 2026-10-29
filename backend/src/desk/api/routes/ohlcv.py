"""`/api/ohlcv` routes: daily, weekly (resampled, Monday 00:00 UTC) and 4H candles."""

import datetime as dt
from enum import StrEnum
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from desk.api.common import candle_sources, get_coin
from desk.api.deps import AsOfDep, SessionDep, require_role
from desk.api.schemas import Envelope, Source
from desk.data import market
from desk.models import Candle4h

router = APIRouter(tags=["market"], dependencies=[Depends(require_role("member"))])


class Timeframe(StrEnum):
    d1 = "1d"
    w1 = "1w"
    h4 = "4h"


class Candle(BaseModel):
    time: dt.datetime  # bar open time, UTC
    open: float | None  # null on close-only Coin Metrics backfill days (D31)
    high: float | None
    low: float | None
    close: float
    volume: float | None


def _candles(df: pd.DataFrame) -> list[Candle]:
    df = df.astype(object).where(pd.notna(df), None)
    return [
        Candle(time=ts.to_pydatetime(), open=r["open"], high=r["high"], low=r["low"],
               close=r["close"], volume=r["volume"])
        for ts, r in df.iterrows()
    ]  # fmt: skip


@router.get("/ohlcv/{coin}", response_model=Envelope[list[Candle]], operation_id="getOhlcv")
def get_ohlcv(
    coin: str,
    session: SessionDep,
    as_of: AsOfDep,
    tf: Timeframe = Timeframe.d1,
    start: Annotated[dt.date | None, Query()] = None,
    end: Annotated[dt.date | None, Query(description="Inclusive; capped by as_of")] = None,
) -> Envelope[list[Candle]]:
    symbol = get_coin(session, coin).symbol
    stop = min(d for d in (as_of, end) if d) if (as_of or end) else None
    if tf is Timeframe.h4:
        q = select(Candle4h).where(Candle4h.coin == symbol).order_by(Candle4h.ts)
        if start:
            q = q.where(Candle4h.ts >= dt.datetime.combine(start, dt.time(), dt.UTC))
        if stop:
            q = q.where(
                Candle4h.ts < dt.datetime.combine(stop, dt.time(), dt.UTC) + dt.timedelta(days=1)
            )
        rows = list(session.scalars(q))
        data = [Candle(time=r.ts, open=r.open, high=r.high, low=r.low, close=r.close,
                       volume=r.volume) for r in rows]  # fmt: skip
        last = data[-1].time.date() if data else None
        return Envelope(as_of=last, sources=[Source(name="coinbase", detail=f"candles_4h:{symbol}",
                                                    last_date=last)], data=data)  # fmt: skip
    daily = market.load_daily(session, symbol, stop)
    bars = market.resample_weekly(daily) if tf is Timeframe.w1 else daily
    if start:
        bars = bars[bars.index >= pd.Timestamp(start, tz="UTC")]
    last_date, sources = candle_sources(session, symbol, stop)
    return Envelope(as_of=last_date, sources=sources, data=_candles(bars))
