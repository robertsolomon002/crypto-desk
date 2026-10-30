"""Coin summary for the Overview cards: last close, 1d/7d/30d change, ATH distance and regime."""

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from desk.analytics._frames import highs, truncate
from desk.analytics.regime import regime

CHANGE_DAYS = (1, 7, 30)


@dataclass(frozen=True)
class Summary:
    date: dt.date | None
    close: float | None
    change_1d: float | None  # close / close N calendar days earlier - 1
    change_7d: float | None
    change_30d: float | None
    ath: float | None  # highest high (close on close-only days, D31)
    ath_date: dt.date | None
    ath_distance: float | None  # close / ath - 1 (<= 0)
    regime: str


def _change(close: pd.Series, days: int) -> float | None:
    """Change against the last close on or before `days` calendar days ago (gaps tolerated)."""
    then = close.loc[: close.index[-1] - pd.Timedelta(days=days)]
    if then.empty:
        return None
    return float(close.iloc[-1] / then.iloc[-1] - 1)


def coin_summary(daily: pd.DataFrame, as_of: dt.date | None = None) -> Summary:
    d = truncate(daily, as_of)
    label = regime(d).current
    if d.empty:
        return Summary(None, None, None, None, None, None, None, None, label)
    close = d["close"]
    last = float(close.iloc[-1])
    h = highs(d)
    ath = float(h.max())
    c1, c7, c30 = (_change(close, n) for n in CHANGE_DAYS)
    return Summary(close.index[-1].date(), last, c1, c7, c30, ath, h.idxmax().date(),
                   last / ath - 1, label)  # fmt: skip
