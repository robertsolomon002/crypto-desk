"""Resolve finished signal weeks into `signal_outcomes` (Section 3.5 step 2, D51).

A signal for week W (a Monday) is made from data up to W - 1 day and covers the daily candles
W .. W + 6. Once all seven have closed, one outcome row is written per signal (never updated):

- `reference_close`: the close on W - 1 (what the signal saw last);
- `week_close`: the close on W + 6; "up" means week_close > reference_close;
- `direction_hit`: lean_long and up, or flat and not up;
- `brier`: (P(up) - up)^2 with P(up) = confidence for lean_long, 1 - confidence for flat;
- `first_hit` (signals with both an invalidation and a target): which the daily lows and highs
  touched first; a day that touches both counts as invalidation (conservative); else `neither`;
- `paper_pnl` (lean_long): bought at the reference close, sold at the invalidation or target
  if one was hit first, else at the week close, with `signals.paper_cost_per_side` on each
  side; flat weeks are 0.

Stage 7.2's scorecard aggregates these rows.
"""

import datetime as dt
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk.data import market
from desk.models import Signal, SignalOutcome

WEEK = dt.timedelta(days=7)


@dataclass(frozen=True)
class Outcome:
    reference_close: float
    week_close: float
    direction_hit: bool
    brier: float
    first_hit: str | None
    paper_pnl: float


def first_hit(days: pd.DataFrame, invalidation: float | None, target: float | None) -> str | None:
    if invalidation is None or target is None:
        return None
    for _, day in days.iterrows():
        low = day["low"] if pd.notna(day["low"]) else day["close"]
        high = day["high"] if pd.notna(day["high"]) else day["close"]
        if low <= invalidation:
            return "invalidation"  # also when the target was touched the same day
        if high >= target:
            return "target"
    return "neither"


def outcome(signal: Signal, reference_close: float, days: pd.DataFrame, cost: float) -> Outcome:
    """`days` are the week's seven daily candles in order."""
    week_close = float(days["close"].iloc[-1])
    up = week_close > reference_close
    lean = signal.stance == "lean_long"
    p_up = signal.confidence if lean else 1 - signal.confidence
    hit = first_hit(days, signal.invalidation, signal.target)
    pnl = 0.0
    if lean:
        exit_price = {"invalidation": signal.invalidation, "target": signal.target}.get(
            hit or "", week_close
        )
        pnl = (exit_price * (1 - cost)) / (reference_close * (1 + cost)) - 1
    return Outcome(
        reference_close=reference_close,
        week_close=week_close,
        direction_hit=up if lean else not up,
        brier=(p_up - (1.0 if up else 0.0)) ** 2,
        first_hit=hit,
        paper_pnl=float(pnl),
    )


def resolve(
    session: Session, today: dt.date, cost: float, write: bool = True
) -> list[tuple[Signal, Outcome]]:
    """Every unresolved signal whose week has fully closed by `today` - 1 (UTC). Weeks whose
    candles are incomplete stay unresolved. Flushes the new rows when `write`."""
    done = select(SignalOutcome.signal_id)
    pending = session.scalars(
        select(Signal)
        .where(Signal.week + WEEK <= today, Signal.id.not_in(done))
        .order_by(Signal.week, Signal.coin, Signal.id)
    ).all()
    out: list[tuple[Signal, Outcome]] = []
    frames: dict[str, pd.DataFrame] = {}
    for sig in pending:
        if sig.coin not in frames:
            frames[sig.coin] = market.load_daily(session, sig.coin, today - dt.timedelta(days=1))
        daily = frames[sig.coin]
        dates = [d.date() for d in daily.index]
        ref_day = sig.week - dt.timedelta(days=1)
        needed = [sig.week + dt.timedelta(days=i) for i in range(7)]
        if ref_day not in dates or any(d not in dates for d in needed):
            continue
        by_date = daily.set_axis(dates)
        res = outcome(sig, float(by_date.loc[ref_day, "close"]), by_date.loc[needed], cost)
        out.append((sig, res))
        if write:
            session.add(SignalOutcome(signal_id=sig.id, **res.__dict__))
    if write:
        session.flush()
    return out
