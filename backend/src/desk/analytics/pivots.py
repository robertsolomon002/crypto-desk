"""Zigzag swing pivots with a volatility-scaled reversal threshold.

A swing reverses when price moves at least `thr_t = clip(k * sigma_t, floor, cap)` from the
running extreme, where sigma_t is the rolling standard deviation of log returns of the bars
used (daily or weekly). Highs and lows drive the swings (closes on close-only rows). Every pivot
but the last is confirmed, with the bar that confirmed it; the last one is the running extreme
of the open leg and can still move.
"""

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from desk.analytics._frames import highs, log_returns, lows, truncate

DEFAULTS = {"1d": {"k": 4.0, "floor": 0.05, "cap": 0.35, "vol_window": 30},
            "1w": {"k": 2.0, "floor": 0.10, "cap": 0.50, "vol_window": 26}}  # fmt: skip


@dataclass(frozen=True)
class Pivot:
    kind: str  # high | low
    date: dt.date
    price: float
    confirmed: bool
    confirmed_on: dt.date | None  # the bar whose move confirmed the reversal


def thresholds(bars: pd.DataFrame, k: float, floor: float, cap: float, vol_window: int):
    sigma = log_returns(bars["close"]).rolling(vol_window, min_periods=vol_window).std()
    return (k * sigma).clip(floor, cap).fillna(cap).to_numpy()


def zigzag(
    bars: pd.DataFrame,
    as_of: dt.date | None = None,
    k: float = 4.0,
    floor: float = 0.05,
    cap: float = 0.35,
    vol_window: int = 30,
) -> list[Pivot]:
    """Alternating swing highs and lows, oldest first."""
    b = truncate(bars, as_of)
    if b.empty:
        return []
    hi, lo = highs(b).to_numpy(), lows(b).to_numpy()
    thr = thresholds(b, k, floor, cap, vol_window)
    dates = [ts.date() for ts in b.index]
    pivots: list[Pivot] = []

    trend = 0  # 0 unknown, 1 up (tracking a high), -1 down (tracking a low)
    hi_i, lo_i = 0, 0  # running extremes while the trend is unknown
    ext_i = 0
    for i in range(1, len(b)):
        if trend == 0:
            if hi[i] > hi[hi_i]:
                hi_i = i
            if lo[i] < lo[lo_i]:
                lo_i = i
            if hi[i] >= lo[lo_i] * (1 + thr[i]) and lo_i < i:
                pivots.append(Pivot("low", dates[lo_i], float(lo[lo_i]), True, dates[i]))
                trend, ext_i = 1, i
            elif lo[i] <= hi[hi_i] * (1 - thr[i]) and hi_i < i:
                pivots.append(Pivot("high", dates[hi_i], float(hi[hi_i]), True, dates[i]))
                trend, ext_i = -1, i
        elif trend == 1:
            if hi[i] > hi[ext_i]:
                ext_i = i
            elif lo[i] <= hi[ext_i] * (1 - thr[i]):
                pivots.append(Pivot("high", dates[ext_i], float(hi[ext_i]), True, dates[i]))
                trend, ext_i = -1, i
        else:
            if lo[i] < lo[ext_i]:
                ext_i = i
            elif hi[i] >= lo[ext_i] * (1 + thr[i]):
                pivots.append(Pivot("low", dates[ext_i], float(lo[ext_i]), True, dates[i]))
                trend, ext_i = 1, i
    if trend == 1:
        pivots.append(Pivot("high", dates[ext_i], float(hi[ext_i]), False, None))
    elif trend == -1:
        pivots.append(Pivot("low", dates[ext_i], float(lo[ext_i]), False, None))
    return pivots


def pivots_frame(pivots: list[Pivot]) -> pd.DataFrame:
    cols = ["kind", "date", "price", "confirmed", "confirmed_on"]
    return pd.DataFrame([[getattr(p, c) for c in cols] for p in pivots], columns=cols)


def swing_returns(pivots: list[Pivot]) -> np.ndarray:
    """Percent move of each leg between consecutive pivots."""
    prices = np.array([p.price for p in pivots])
    return prices[1:] / prices[:-1] - 1 if len(prices) > 1 else np.array([])
