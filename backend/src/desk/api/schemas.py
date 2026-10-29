"""Response models shared by the routes. Every data response carries provenance (D37):
`as_of` (the last date the data covers) and `sources` (where each part came from)."""

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class Source(BaseModel):
    name: str  # e.g. coinbase, coinmetrics, fred, alternative.me, desk.analytics
    detail: str | None = None  # e.g. the series key or analytics function
    url: str | None = None
    last_date: dt.date | None = None


class Envelope[T](BaseModel):
    as_of: dt.date | None = Field(description="Last UTC date the data covers")
    sources: list[Source]
    data: T


class AnalyticsData(BaseModel):
    name: str
    coin: str
    params: dict[str, Any]
    cached: bool
    result: Any


class SeriesPoint(BaseModel):
    date: dt.date
    value: float | None
