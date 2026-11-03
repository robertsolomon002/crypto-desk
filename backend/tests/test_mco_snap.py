"""Snapping extracted wave labels to zigzag pivots (Stage 6.1), on synthetic pivots."""

import datetime as dt

import pytest

from desk.analytics.pivots import Pivot
from desk.mco import snap

D = dt.date
DAYS = [D(2026, 9, 1) + dt.timedelta(days=i) for i in range(60)]
WEEKS = [D(2026, 1, 5) + dt.timedelta(weeks=i) for i in range(40)]
PIVOTS = [
    Pivot("low", D(2026, 9, 10), 50000.0, True, D(2026, 9, 14)),
    Pivot("high", D(2026, 9, 20), 60000.0, True, D(2026, 9, 25)),
    Pivot("low", D(2026, 10, 1), 55000.0, True, D(2026, 10, 5)),
    Pivot("high", D(2026, 10, 20), 64000.0, False, None),
]
TOL = {"bars": 5, "pct": 0.03}


def test_matches_the_nearest_pivot_of_the_right_kind() -> None:
    s = snap.snap_label(PIVOTS, DAYS, "high", D(2026, 9, 22), 59500.0, "1d", TOL)
    assert s.pivot == PIVOTS[1] and s.bars == 2 and s.pct == pytest.approx(0.0084, abs=1e-4)
    # A low label near the same spot must not take the high.
    s = snap.snap_label(PIVOTS, DAYS, "low", D(2026, 9, 22), 59500.0, "1d", TOL)
    assert s.pivot is None and s.note == "unmatched: no low within ±5 bars and ±3% on 1d"


def test_tolerance_edges() -> None:
    assert snap.snap_label(PIVOTS, DAYS, "high", D(2026, 9, 25), 60000.0, "1d", TOL).bars == 5
    assert snap.snap_label(PIVOTS, DAYS, "high", D(2026, 9, 26), 60000.0, "1d", TOL).pivot is None
    assert snap.snap_label(PIVOTS, DAYS, "high", D(2026, 9, 20), 58300.0, "1d", TOL).pivot  # 2.9%
    assert snap.snap_label(PIVOTS, DAYS, "high", D(2026, 9, 20), 58000.0, "1d", TOL).pivot is None


def test_unknown_kind_takes_either_and_ties_go_to_the_closer_date() -> None:
    pivots = [
        Pivot("high", D(2026, 9, 18), 60000.0, True, None),
        Pivot("high", D(2026, 9, 22), 60000.0, True, None),
    ]
    s = snap.snap_label(pivots, DAYS, None, D(2026, 9, 21), 60000.0, "1d", TOL)
    assert s.pivot == pivots[1]


def test_unconfirmed_last_pivot_and_dates_past_the_data() -> None:
    s = snap.snap_label(PIVOTS, DAYS, "high", D(2026, 10, 21), 64500.0, "1d", TOL)
    assert s.pivot == PIVOTS[3]
    s = snap.snap_label(PIVOTS, DAYS, "high", D(2026, 12, 1), 64500.0, "1d", TOL)
    assert s.note == "unmatched: date after the last bar"
    assert snap.snap_label([], [], "high", D(2026, 9, 1), 1.0, "1d", TOL).note.endswith("data")


def test_weekly_scaling_counts_weekly_bars() -> None:
    weekly = [Pivot("high", D(2026, 3, 2), 100.0, True, None)]
    tol = {"bars": 2, "pct": 0.06}
    assert snap.snap_label(weekly, WEEKS, "high", D(2026, 3, 18), 95.0, "1w", tol).bars == 2
    assert snap.snap_label(weekly, WEEKS, "high", D(2026, 3, 25), 95.0, "1w", tol).pivot is None


@pytest.mark.parametrize(
    ("raw", "tf"),
    [
        ("1D", "1d"),
        ("daily", "1d"),
        ("4h", "1d"),
        (None, "1d"),
        ("1W", "1w"),
        ("Weekly", "1w"),
        ("monthly", "1w"),
    ],
)
def test_timeframes(raw, tf) -> None:
    assert snap.snap_timeframe(raw) == tf


def test_tolerances_come_from_settings() -> None:
    assert snap.tolerances("1d") == {"bars": 5, "pct": 0.03}
    assert snap.tolerances("1w") == {"bars": 2, "pct": 0.06}
