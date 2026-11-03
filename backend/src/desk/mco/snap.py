"""Snap extracted wave labels to zigzag pivots (Section 3.4 step 3, D48).

Each `pivot_label` is matched to the nearest pivot of the same kind (high or low) on its
timeframe within a tolerance window: `mco.snap` in `settings.yaml`, default ±5 bars and ±3% on
1D and ±2 bars and ±6% on 1W. Sub-daily labels (4h, 1h) snap on 1D and multi-week ones on 1W.
Pivots are computed as of the day before the video's publication date (the last closed bar
when he recorded), the same way `/api/pivots` computes them.

The distance score is bars/tol_bars + |pct|/tol_pct; the lowest score wins and ties go to the
closer date. Every result is stored as `pending`; an unmatched label keeps a null pivot and a
`match_note` saying why. Only labels Rob approves are ever shown to members (Decision 7).
"""

import bisect
import datetime as dt
from dataclasses import dataclass

from desk.analytics.pivots import Pivot
from desk.config import load_app_settings

DEFAULT_TOL = {"1d": {"bars": 5, "pct": 0.03}, "1w": {"bars": 2, "pct": 0.06}}


@dataclass(frozen=True)
class Snap:
    timeframe: str  # 1d | 1w (the chart we snapped on)
    pivot: Pivot | None
    bars: int | None
    pct: float | None
    note: str | None


def snap_timeframe(chart_timeframe: str | None) -> str:
    tf = (chart_timeframe or "").strip().lower().replace(" ", "")
    if tf in ("1w", "w", "weekly", "week", "1week", "2w", "1mo", "monthly", "month", "3d"):
        return "1w"
    return "1d"  # 1d, daily, 4h, 1h, unknown


def tolerances(timeframe: str) -> dict:
    cfg = (load_app_settings().get("mco") or {}).get("snap") or {}
    return {**DEFAULT_TOL[timeframe], **(cfg.get(timeframe) or {})}


def bar_index(bar_dates: list[dt.date], day: dt.date) -> int:
    """Index of the bar that contains `day` (the last bar starting on or before it)."""
    return max(0, bisect.bisect_right(bar_dates, day) - 1)


def snap_label(
    pivots: list[Pivot],
    bar_dates: list[dt.date],
    kind: str | None,
    approx_date: dt.date,
    approx_price: float,
    timeframe: str,
    tol: dict | None = None,
) -> Snap:
    tol = tol or tolerances(timeframe)
    tb, tp = int(tol["bars"]), float(tol["pct"])
    if not bar_dates:
        return Snap(timeframe, None, None, None, "unmatched: no price data")
    if approx_date > bar_dates[-1] + dt.timedelta(days=7 if timeframe == "1w" else 1):
        return Snap(timeframe, None, None, None, "unmatched: date after the last bar")
    at = bar_index(bar_dates, approx_date)
    best: tuple[float, int, Pivot, int, float] | None = None
    for p in pivots:
        if kind and p.kind != kind:
            continue
        bars = abs(bar_index(bar_dates, p.date) - at)
        pct = p.price / approx_price - 1
        if bars > tb or abs(pct) > tp:
            continue
        key = (bars / tb + abs(pct) / tp, bars, p, bars, pct)
        if best is None or key[:2] < best[:2]:
            best = key
    if best is None:
        what = kind or "pivot"
        return Snap(
            timeframe,
            None,
            None,
            None,
            f"unmatched: no {what} within ±{tb} bars and ±{tp:.0%} on {timeframe}",
        )
    _, _, pivot, bars, pct = best
    return Snap(timeframe, pivot, bars, round(pct, 4), None)
