"""Regime label with the frozen rules of D34 (docs/DECISIONS.md). Do not tune these."""

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from desk.analytics._frames import truncate
from desk.analytics.indicators import realized_vol, sma

MIN_DAYS = 365
VOL_WINDOW = 30
VOL_LOOKBACK = 365
VOL_QUANTILE = 0.9
SLOPE_DAYS = 20

LABELS = ("insufficient_data", "high-vol", "uptrend", "downtrend", "range")


@dataclass(frozen=True)
class Regime:
    current: str
    date: dt.date | None
    inputs: dict[str, float | None]  # the values behind the current label
    labels: pd.Series  # label per day


def regime_frame(daily: pd.DataFrame, as_of: dt.date | None = None) -> pd.DataFrame:
    """Per day: the rule inputs and the label (first matching rule in D34 order)."""
    close = truncate(daily, as_of)["close"]
    sma50, sma200 = sma(close, 50), sma(close, 200)
    sma50_prev = sma50.shift(SLOPE_DAYS)
    vol = realized_vol(close, VOL_WINDOW)
    vol_thr = vol.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK).quantile(VOL_QUANTILE)
    enough = np.arange(1, len(close) + 1) >= MIN_DAYS
    conditions = [
        ~enough,
        (vol > vol_thr).to_numpy(),
        ((close > sma200) & (sma50 > sma200) & (sma50 > sma50_prev)).to_numpy(),
        ((close < sma200) & (sma50 < sma200) & (sma50 < sma50_prev)).to_numpy(),
    ]
    label = np.select(conditions, list(LABELS[:4]), default="range")
    return pd.DataFrame(
        {"close": close, "sma50": sma50, "sma200": sma200, "sma50_prev": sma50_prev,
         "vol30": vol, "vol30_p90": vol_thr, "label": label},
        index=close.index,
    )  # fmt: skip


def regime(daily: pd.DataFrame, as_of: dt.date | None = None) -> Regime:
    frame = regime_frame(daily, as_of)
    if frame.empty:
        return Regime("insufficient_data", None, {}, frame["label"])
    last = frame.iloc[-1]
    inputs = {k: (None if pd.isna(last[k]) else float(last[k])) for k in frame.columns[:-1]}
    return Regime(str(last["label"]), frame.index[-1].date(), inputs, frame["label"])
