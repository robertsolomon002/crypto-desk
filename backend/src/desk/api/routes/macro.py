"""`/api/macro` routes: FRED series (with release lags, D32), Fear & Greed, dominance."""

import datetime as dt
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from desk.analytics._frames import to_jsonable
from desk.api.deps import AsOfDep, SessionDep, require_role
from desk.api.schemas import Envelope, SeriesPoint, Source
from desk.data import dominance, fred, sentiment

router = APIRouter(prefix="/macro", tags=["macro"], dependencies=[Depends(require_role("member"))])


class MacroSeries(BaseModel):
    id: str
    label: str
    units: str
    release_lag_days: int


class MacroData(BaseModel):
    series: list[MacroSeries]
    rows: list[dict[str, Any]]  # {"date": ..., "<FRED id>": value | null, ...}


class DominanceData(BaseModel):
    rows: list[dict[str, Any]]  # {"date": ..., "btc": pct, "eth": pct}


def _since(df: pd.DataFrame, start: dt.date | None) -> pd.DataFrame:
    return df[df.index >= pd.Timestamp(start, tz="UTC")] if start else df


def _last(df: pd.DataFrame | pd.Series) -> dt.date | None:
    return df.index.max().date() if len(df) else None


@router.get("", response_model=Envelope[MacroData], operation_id="getMacro")
def get_macro(
    session: SessionDep, as_of: AsOfDep, start: dt.date | None = None
) -> Envelope[MacroData]:
    """FRED series as published by `as_of` (each row needs date + release lag <= as_of)."""
    config = fred.load_config()
    df = _since(fred.load_macro(session, as_of, config), start).dropna(how="all")
    sources = [
        Source(name="fred", detail=s.id, url=f"https://fred.stlouisfed.org/series/{s.id}",
               last_date=_last(df[s.id].dropna()))
        for s in config
    ]  # fmt: skip
    meta = [MacroSeries(id=s.id, label=s.label, units=s.units,
                        release_lag_days=s.release_lag_days) for s in config]  # fmt: skip
    return Envelope(as_of=as_of or _last(df), sources=sources,
                    data=MacroData(series=meta, rows=to_jsonable(df)))  # fmt: skip


@router.get("/fng", response_model=Envelope[list[SeriesPoint]], operation_id="getFearGreed")
def get_fng(
    session: SessionDep, as_of: AsOfDep, start: dt.date | None = None
) -> Envelope[list[SeriesPoint]]:
    """Daily Crypto Fear & Greed index (0 to 100)."""
    s = sentiment.load_fng(session, as_of)
    s = s[s.index >= pd.Timestamp(start, tz="UTC")] if start else s
    last = _last(s)
    src = Source(name=sentiment.SOURCE, detail=sentiment.KEY, url=sentiment.URL, last_date=last)
    return Envelope(as_of=last, sources=[src], data=to_jsonable(s))


@router.get("/dominance", response_model=Envelope[DominanceData], operation_id="getDominance")
def get_dominance(
    session: SessionDep, as_of: AsOfDep, start: dt.date | None = None
) -> Envelope[DominanceData]:
    """BTC and ETH dominance in percent: daily snapshots from Stage 1.2 on (no free history)."""
    df = _since(dominance.load_dominance(session, as_of), start).dropna(how="all")
    last = _last(df)
    src = Source(name=dominance.SOURCE, detail="dominance:btc,eth", last_date=last)
    return Envelope(as_of=last, sources=[src], data=DominanceData(rows=to_jsonable(df)))
