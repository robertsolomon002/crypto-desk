"""Synthetic market and on-chain frames shaped like the real data (same columns, UTC index)."""

import datetime as dt

import numpy as np
import pandas as pd

from desk.analytics.inputs import Inputs
from desk.data.market import OHLCV


def frame(closes, start: str = "2024-01-01", ohlc: bool = False) -> pd.DataFrame:
    """A daily frame from a list of closes; close-only (like the Coin Metrics backfill) unless
    `ohlc`, in which case open = previous close and high/low = max/min(open, close)."""
    close = pd.Series(np.asarray(closes, dtype="float64"))
    idx = pd.date_range(start, periods=len(close), freq="D", tz="UTC", name="date")
    df = pd.DataFrame(index=idx, columns=OHLCV, dtype="float64")
    df["close"] = close.to_numpy()
    if ohlc:
        opens = close.shift(1).fillna(close)
        df["open"] = opens.to_numpy()
        df["high"] = np.maximum(opens, close).to_numpy()
        df["low"] = np.minimum(opens, close).to_numpy()
        df["volume"] = 1.0
    df["source"] = "coinbase" if ohlc else "coinmetrics"
    return df


def random_daily(
    start: dt.date, end: dt.date, seed: int, close_only_until: dt.date | None = None
) -> pd.DataFrame:
    """A random walk with OHLCV; days before `close_only_until` are close-only."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, end, freq="D", tz="UTC", name="date")
    rets = rng.normal(0.0008, 0.035, len(idx))
    close = 10.0 * np.exp(np.cumsum(rets))
    opens = np.concatenate([[close[0]], close[:-1]])
    wick = np.abs(rng.normal(0, 0.015, (2, len(idx))))
    df = pd.DataFrame(
        {"open": opens, "high": np.maximum(opens, close) * (1 + wick[0]),
         "low": np.minimum(opens, close) * (1 - wick[1]), "close": close,
         "volume": rng.uniform(1, 2, len(idx)), "source": "coinbase"},
        index=idx,
    )  # fmt: skip
    if close_only_until is not None:
        early = df.index < pd.Timestamp(close_only_until, tz="UTC")
        df.loc[early, ["open", "high", "low", "volume"]] = np.nan
        df.loc[early, "source"] = "coinmetrics"
    return df


def random_onchain(daily: pd.DataFrame, seed: int, hash_until: dt.date | None = None):
    rng = np.random.default_rng(seed)
    n = len(daily)
    supply = np.linspace(1e7, 2e7, n)
    mvrv = np.exp(np.cumsum(rng.normal(0, 0.02, n))) * 1.5
    df = pd.DataFrame(
        {"CapMrktCurUSD": daily["close"].to_numpy() * supply, "CapMVRVCur": mvrv,
         "SplyCur": supply, "AdrActCnt": rng.uniform(5e5, 1e6, n),
         "HashRate": rng.uniform(1e8, 2e8, n)},
        index=daily.index,
    )  # fmt: skip
    if hash_until is not None:
        df.loc[df.index > pd.Timestamp(hash_until, tz="UTC"), "HashRate"] = np.nan
    return df


def synthetic_inputs() -> Inputs:
    """BTC from 2010-07-18 (close-only until 2015-07-20), ETH from 2016-05-18, SOL from
    2021-06-17, all to 2026-10-28, with on-chain frames for BTC and ETH; repo cycles.yaml."""
    end = dt.date(2026, 10, 28)
    btc = random_daily(dt.date(2010, 7, 18), end, 1, close_only_until=dt.date(2015, 7, 20))
    eth = random_daily(dt.date(2016, 5, 18), end, 2)
    sol = random_daily(dt.date(2021, 6, 17), end, 3)
    return Inputs(
        daily={"BTC": btc, "ETH": eth, "SOL": sol},
        onchain={"BTC": random_onchain(btc, 4),
                 "ETH": random_onchain(eth, 5, hash_until=dt.date(2022, 9, 14))},
    )  # fmt: skip
