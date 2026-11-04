"""Coin-flip and trend-rule baselines (Section 3.5, Stage 7.1, D51).

- **Coin flip:** always `flat` at 0.5 (no view either way).
- **Trend rule:** `lean_long` at 0.6 if the last complete weekly close is above its 20-week SMA,
  else `flat` at 0.6. The roadmap's "flat with 0.4" is the chance of a higher close; stored
  signals carry the confidence that the stance is right, which can't go below 0.5 (D51).

Both are pure functions of the daily candles up to `as_of` (no look-ahead) and set no levels.
"""

import datetime as dt
from typing import Any

import pandas as pd

from desk.analytics._frames import truncate
from desk.analytics.indicators import sma
from desk.data.market import resample_weekly
from desk.signals.chain import Proposed


def coinflip(coin: str) -> Proposed:
    return Proposed(
        coin=coin,
        source="coinflip",
        stance="flat",
        confidence=0.5,
        rationale="Coin-flip baseline: always flat at 0.5.",
    )


def trend(
    coin: str, daily: pd.DataFrame, as_of: dt.date, cfg: dict[str, Any] | None = None
) -> Proposed | None:
    """None when there are fewer complete weeks than the SMA needs."""
    cfg = cfg or {}
    n = int(cfg.get("sma_weeks", 20))
    weekly = resample_weekly(truncate(daily, as_of))
    if len(weekly) < n:
        return None
    close = float(weekly["close"].iloc[-1])
    average = float(sma(weekly["close"], n).iloc[-1])
    week = weekly.index[-1].date()
    if close > average:
        return Proposed(
            coin=coin,
            source="trend",
            stance="lean_long",
            confidence=float(cfg.get("long_confidence", 0.6)),
            rationale=f"Trend rule: the week of {week} closed at {close:.6g}, above "
            f"its {n}-week SMA {average:.6g}.",
        )
    return Proposed(
        coin=coin,
        source="trend",
        stance="flat",
        confidence=float(cfg.get("flat_confidence", 0.6)),
        rationale=f"Trend rule: the week of {week} closed at {close:.6g}, at or "
        f"below its {n}-week SMA {average:.6g}.",
    )
