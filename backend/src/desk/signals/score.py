"""The scorecard (Decision 8, Stage 7.2, D52): aggregates of the `signal_outcomes` rows that
`signals/resolve.py` writes, per source and per (source, coin), and cumulatively by week.

Per group:
- **direction hit rate:** hits / resolved signals (`lean_long` and the week closed higher, or
  `flat` and it didn't);
- **Brier score:** the mean of (P(up) - up)^2 on the confidence (0 is perfect, the coin flip
  always scores 0.25);
- **target before invalidation:** of the signals with both levels, the share whose target was
  touched first within the week; a day touching both counts as invalidation (resolve.py);
- **paper P&L:** `lean_long` weeks bought at the reference close with
  `signals.paper_cost_per_side` on each side (already in `paper_pnl`); flat weeks are 0. Per
  (source, coin) the weekly returns are compounded. Per source each week is the equal-weight
  mean over that source's coins that week, then compounded;
- **early days:** fewer than `EARLY_WEEKS` distinct weeks, too few to tell skill from luck.

Pure functions of the resolved rows, so the hand-computed tests pin the arithmetic.
"""

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk.models import Signal, SignalOutcome
from desk.signals.chain import SOURCES

EARLY_WEEKS = 12


@dataclass(frozen=True)
class Resolved:
    """One signal with its outcome."""

    week: dt.date
    coin: str
    source: str
    stance: str
    confidence: float
    direction_hit: bool
    brier: float
    first_hit: str | None  # target | invalidation | neither; None without both levels
    paper_pnl: float


@dataclass(frozen=True)
class Stats:
    signals: int
    weeks: int
    hits: int
    hit_rate: float | None
    brier: float | None
    with_levels: int
    target_first: int
    invalidation_first: int
    neither: int
    target_first_rate: float | None
    long_weeks: int
    paper_return: float  # compounded, after costs
    early_days: bool


@dataclass(frozen=True)
class Point:
    """Cumulative values up to and including `week`."""

    week: dt.date
    signals: int
    hit_rate: float
    brier: float
    paper_return: float


@dataclass
class Scorecard:
    version: int
    weeks: list[dt.date]
    by_source: dict[str, Stats] = field(default_factory=dict)
    by_coin: dict[tuple[str, str], Stats] = field(default_factory=dict)  # (source, coin)
    cumulative: dict[str, list[Point]] = field(default_factory=dict)  # per source


def weekly_returns(rows: Iterable[Resolved]) -> dict[dt.date, float]:
    """Each week's equal-weight mean paper P&L over the rows of that week."""
    per_week: dict[dt.date, list[float]] = defaultdict(list)
    for r in rows:
        per_week[r.week].append(r.paper_pnl)
    return {w: sum(v) / len(v) for w, v in sorted(per_week.items())}


def compound(returns: Iterable[float]) -> float:
    total = 1.0
    for r in returns:
        total *= 1 + r
    return total - 1


def stats(rows: list[Resolved]) -> Stats:
    n = len(rows)
    hits = sum(r.direction_hit for r in rows)
    firsts = [r.first_hit for r in rows if r.first_hit is not None]
    target = firsts.count("target")
    weeks = {r.week for r in rows}
    return Stats(
        signals=n,
        weeks=len(weeks),
        hits=hits,
        hit_rate=hits / n if n else None,
        brier=sum(r.brier for r in rows) / n if n else None,
        with_levels=len(firsts),
        target_first=target,
        invalidation_first=firsts.count("invalidation"),
        neither=firsts.count("neither"),
        target_first_rate=target / len(firsts) if firsts else None,
        long_weeks=sum(r.stance == "lean_long" for r in rows),
        paper_return=compound(weekly_returns(rows).values()),
        early_days=len(weeks) < EARLY_WEEKS,
    )


def cumulative(rows: list[Resolved]) -> list[Point]:
    out: list[Point] = []
    seen: list[Resolved] = []
    returns = weekly_returns(rows)
    growth = 1.0
    for week in sorted(returns):
        seen += [r for r in rows if r.week == week]
        growth *= 1 + returns[week]
        out.append(
            Point(
                week=week,
                signals=len(seen),
                hit_rate=sum(r.direction_hit for r in seen) / len(seen),
                brier=sum(r.brier for r in seen) / len(seen),
                paper_return=growth - 1,
            )
        )
    return out


def _source_order(source: str) -> int:
    return SOURCES.index(source) if source in SOURCES else len(SOURCES)


def scorecard(rows: list[Resolved], version: int) -> Scorecard:
    sources = sorted({r.source for r in rows}, key=lambda s: (_source_order(s), s))
    card = Scorecard(version=version, weeks=sorted({r.week for r in rows}))
    for source in sources:
        mine = [r for r in rows if r.source == source]
        card.by_source[source] = stats(mine)
        card.cumulative[source] = cumulative(mine)
        for coin in sorted({r.coin for r in mine}):
            card.by_coin[(source, coin)] = stats([r for r in mine if r.coin == coin])
    return card


def load(session: Session, version: int, include_mco: bool = True) -> list[Resolved]:
    """Every resolved signal of `version`, oldest week first."""
    q = (
        select(Signal, SignalOutcome)
        .join(SignalOutcome, SignalOutcome.signal_id == Signal.id)
        .where(Signal.version == version)
        .order_by(Signal.week, Signal.coin, Signal.id)
    )
    if not include_mco:
        q = q.where(Signal.source != "mco")
    return [
        Resolved(
            week=s.week,
            coin=s.coin,
            source=s.source,
            stance=s.stance,
            confidence=float(s.confidence),
            direction_hit=bool(o.direction_hit),
            brier=float(o.brier or 0.0),
            first_hit=o.first_hit,
            paper_pnl=float(o.paper_pnl or 0.0),
        )
        for s, o in session.execute(q)
    ]
