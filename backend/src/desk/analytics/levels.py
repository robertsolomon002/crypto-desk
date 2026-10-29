"""Key levels: previous week high/low, SMAs, ATH and the latest confirmed swings."""

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from desk.analytics._frames import highs, truncate
from desk.analytics.indicators import sma
from desk.analytics.pivots import DEFAULTS, zigzag
from desk.data.market import resample_weekly


@dataclass(frozen=True)
class Level:
    name: str
    value: float
    date: dt.date | None  # when the level was set, if it is a point (ATH, swing, week)
    distance: float  # value / last close - 1


def key_levels(daily: pd.DataFrame, as_of: dt.date | None = None) -> list[Level]:
    """Levels as of the last close up to `as_of`, in a fixed order; missing ones are skipped."""
    d = truncate(daily, as_of)
    if d.empty:
        return []
    close = d["close"]
    last = float(close.iloc[-1])
    found: list[tuple[str, float, dt.date | None]] = []

    weekly = resample_weekly(d)
    if not weekly.empty:
        week = weekly.index[-1].date()
        found.append(("prev_week_high", float(weekly["high"].iloc[-1]), week))
        found.append(("prev_week_low", float(weekly["low"].iloc[-1]), week))
        sma20w = sma(weekly["close"], 20).iloc[-1]
        found.append(("sma20w", float(sma20w), None))
    for n in (50, 200):
        found.append((f"sma{n}d", float(sma(close, n).iloc[-1]), None))

    h = highs(d)
    found.append(("ath", float(h.max()), h.idxmax().date()))

    pivots = [p for p in zigzag(d, **DEFAULTS["1d"]) if p.confirmed]
    for kind in ("high", "low"):
        swing = next((p for p in reversed(pivots) if p.kind == kind), None)
        if swing:
            found.append((f"swing_{kind}", swing.price, swing.date))

    return [
        Level(name, value, date, value / last - 1)
        for name, value, date in found
        if not pd.isna(value)
    ]
