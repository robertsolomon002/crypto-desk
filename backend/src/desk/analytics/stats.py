"""Return distributions, drawdowns, rolling volatility and rolling correlations."""

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from desk.analytics._frames import DAY, log_returns, truncate
from desk.analytics.indicators import realized_vol
from desk.data.market import resample_weekly

HORIZONS = ("1d", "1w", "30d")
QUANTILES = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)


def period_returns(daily: pd.DataFrame, horizon: str) -> pd.Series:
    """Simple returns: `1d` consecutive days, `1w` complete Monday weeks (labeled by Monday),
    `30d` rolling 30 calendar days (overlapping, labeled by the end day)."""
    close = daily["close"]
    if horizon == "1d":
        rets = close.pct_change()
        return rets[(close.index.to_series().diff() == DAY).to_numpy()].dropna()
    if horizon == "1w":
        return resample_weekly(daily)["close"].pct_change().dropna()
    if horizon == "30d":
        cal = close.asfreq("D")
        return (cal / cal.shift(30) - 1).dropna()
    raise ValueError(f"horizon must be one of {HORIZONS}")


@dataclass(frozen=True)
class Distribution:
    horizon: str
    count: int
    mean: float | None
    std: float | None
    quantiles: dict[str, float]
    bins: list[float]  # histogram edges (len = counts + 1)
    counts: list[int]
    current_date: dt.date | None  # the latest complete period
    current: float | None
    current_percentile: float | None  # share of periods <= current, 0..100


def return_distribution(
    daily: pd.DataFrame, horizon: str = "1w", as_of: dt.date | None = None, bins: int = 40
) -> Distribution:
    rets = period_returns(truncate(daily, as_of), horizon)
    if rets.empty:
        return Distribution(horizon, 0, None, None, {}, [], [], None, None, None)
    counts, edges = np.histogram(rets.to_numpy(), bins=bins)
    current = float(rets.iloc[-1])
    return Distribution(
        horizon=horizon,
        count=len(rets),
        mean=float(rets.mean()),
        std=float(rets.std()),
        quantiles={f"p{round(q * 100)}": float(rets.quantile(q)) for q in QUANTILES},
        bins=[float(e) for e in edges],
        counts=[int(c) for c in counts],
        current_date=rets.index[-1].date(),
        current=current,
        current_percentile=float((rets <= current).mean() * 100),
    )


def drawdown_series(daily: pd.DataFrame, as_of: dt.date | None = None) -> pd.DataFrame:
    """Close, running all-time-high close and drawdown from it, per day."""
    close = truncate(daily, as_of)["close"]
    peak = close.cummax()
    return pd.DataFrame({"close": close, "peak": peak, "drawdown": close / peak - 1})


def drawdown_episodes(
    daily: pd.DataFrame, as_of: dt.date | None = None, top_n: int = 10
) -> pd.DataFrame:
    """The deepest peak-to-trough episodes on closes. `recovery` is the first close back at the
    peak (None while still under water)."""
    dd = drawdown_series(daily, as_of)
    cols = ["peak_date", "peak", "trough_date", "trough", "depth", "recovery_date", "days"]
    if dd.empty:
        return pd.DataFrame(columns=cols)
    under = dd["drawdown"].to_numpy() < 0
    idx, close = dd.index, dd["close"].to_numpy()
    episodes = []
    i, n = 0, len(dd)
    while i < n:
        if not under[i]:
            i += 1
            continue
        start = i  # first day under water; the peak is the day before
        while i < n and under[i]:
            i += 1
        seg = slice(start, i)
        t = start + int(np.argmin(close[seg]))
        peak_i = start - 1
        recovered = i < n
        episodes.append(
            {"peak_date": idx[peak_i].date(), "peak": close[peak_i],
             "trough_date": idx[t].date(), "trough": close[t],
             "depth": close[t] / close[peak_i] - 1,
             "recovery_date": idx[i].date() if recovered else None,
             "days": ((idx[i] if recovered else idx[-1]) - idx[peak_i]).days}
        )  # fmt: skip
    out = pd.DataFrame(episodes, columns=cols)
    return out.sort_values("depth", kind="stable").head(top_n).reset_index(drop=True)


def rolling_volatility(
    daily: pd.DataFrame, as_of: dt.date | None = None, windows: tuple[int, ...] = (30, 90)
) -> pd.DataFrame:
    close = truncate(daily, as_of)["close"]
    return pd.DataFrame({f"vol{n}": realized_vol(close, n) for n in windows})


def rolling_correlation(
    closes: Mapping[str, pd.Series], as_of: dt.date | None = None, window: int = 90
) -> pd.DataFrame:
    """Rolling correlation of daily log returns for every pair, on dates all coins share."""
    rets = pd.concat(
        {c: log_returns(truncate(s, as_of)) for c, s in closes.items()}, axis=1, join="inner"
    ).dropna()
    coins = list(closes)
    out = {}
    for i, a in enumerate(coins):
        for b in coins[i + 1 :]:
            out[f"{a}/{b}"] = rets[a].rolling(window, min_periods=window).corr(rets[b])
    return pd.DataFrame(out, index=rets.index)
