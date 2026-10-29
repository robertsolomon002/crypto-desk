"""SMA/EMA, Bollinger, RSI, MACD, realized volatility and the weekly bull market support band.

All indicators are causal: values at day t use closes up to t only (D33). Warm-up periods are
NaN rather than partial-window values.
"""

import datetime as dt
import math

import numpy as np
import pandas as pd

from desk.analytics._frames import log_returns, truncate
from desk.data.market import resample_weekly

ANNUALIZE = math.sqrt(365)  # crypto trades every day


def sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n, min_periods=n).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    """Recursive EMA (alpha = 2 / (n + 1)) seeded with the first value; NaN for the first n - 1."""
    return close.ewm(span=n, adjust=False, min_periods=n).mean()


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """Middle band SMA(n), bands at ±k population standard deviations (ddof=0)."""
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return pd.DataFrame({"bb_mid": mid, "bb_upper": mid + k * sd, "bb_lower": mid - k * sd})


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI: the first average is the mean of the first n changes, then
    avg_t = (avg_{t-1} * (n - 1) + x_t) / n. 100 when there are no losses, 50 when flat."""
    delta = close.diff().to_numpy()
    out = np.full(len(close), np.nan)
    if len(close) <= n:
        return pd.Series(out, index=close.index)
    gains = np.clip(delta, 0, None)
    losses = np.clip(-delta, 0, None)
    avg_g = gains[1 : n + 1].mean()
    avg_l = losses[1 : n + 1].mean()
    for i in range(n, len(close)):
        if i > n:
            avg_g = (avg_g * (n - 1) + gains[i]) / n
            avg_l = (avg_l * (n - 1) + losses[i]) / n
        if avg_l == 0:
            out[i] = 50.0 if avg_g == 0 else 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return pd.Series(out, index=close.index)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def realized_vol(close: pd.Series, n: int = 30) -> pd.Series:
    """Annualized standard deviation of daily log returns over n days (× √365)."""
    return log_returns(close).rolling(n, min_periods=n).std(ddof=1) * ANNUALIZE


def weekly_band(daily: pd.DataFrame) -> pd.DataFrame:
    """20-week SMA and 21-week EMA of complete weekly closes, mapped onto daily rows.

    A week's value becomes known when the week closes, so it applies from the next Monday on.
    """
    weekly = resample_weekly(daily)
    band = pd.DataFrame(  # arrays, not Series: a Series would align to the shifted index
        {"sma20w": sma(weekly["close"], 20).to_numpy(),
         "ema21w": ema(weekly["close"], 21).to_numpy()},
        index=weekly.index + pd.Timedelta(days=7),
    )  # fmt: skip
    return band.reindex(band.index.union(daily.index)).ffill().reindex(daily.index)


def indicators(daily: pd.DataFrame, as_of: dt.date | None = None) -> pd.DataFrame:
    """Every chart indicator for one coin, one row per day up to `as_of`."""
    d = truncate(daily, as_of)
    close = d["close"]
    out = pd.DataFrame({"close": close})
    for n in (20, 50, 200):
        out[f"sma{n}"] = sma(close, n)
    for n in (20, 50, 200):
        out[f"ema{n}"] = ema(close, n)
    out = out.join(bollinger(close)).join(macd(close))
    out["rsi14"] = rsi(close)
    out["vol30"] = realized_vol(close, 30)
    out["vol90"] = realized_vol(close, 90)
    return out.join(weekly_band(d))
