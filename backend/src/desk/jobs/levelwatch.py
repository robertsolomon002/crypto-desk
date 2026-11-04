"""Daily level watch (Section 3.5, Stage 7.1, D51). No LLM.

For the latest closed day D (yesterday, UTC) and each active coin, a level L is crossed when
the close moved through it: close(D-1) < L <= close(D) (up) or close(D-1) > L >= close(D)
(down). Levels:
- this signal week's levels (entry low and high, invalidation, target) from the desk and MCO
  rows, for the week that contains D;
- key levels (`analytics.levels.key_levels`) as of D-1, so a level isn't moved by the close
  that crosses it.

All crossings of one run go out as one `level_cross` alert. MCO-derived crossings go to the
alert channels but never to the summary printed in the (public) workflow log. A run that finds
a successful `levelwatch` run already recorded for D sends nothing, unless `force`.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from desk.models import CandleDaily, JobRun, Signal
from desk.notify import Alert, send

JOB = "levelwatch"
SIGNAL_LEVELS = ("entry_low", "entry_high", "invalidation", "target")
LEVEL_SOURCES = ("desk", "mco")
KEY_LABELS = {
    "prev_week_high": "previous week high",
    "prev_week_low": "previous week low",
    "sma20w": "20-week SMA",
    "sma50d": "50-day SMA",
    "sma200d": "200-day SMA",
    "ath": "all-time high",
    "swing_high": "swing high",
    "swing_low": "swing low",
}
SIGNAL_LABELS = {
    "entry_low": "entry low",
    "entry_high": "entry high",
    "invalidation": "invalidation",
    "target": "target",
}


@dataclass(frozen=True)
class Crossing:
    coin: str
    day: dt.date
    label: str
    level: float
    direction: Literal["up", "down"]
    prev_close: float
    close: float
    source: str  # key | desk | mco

    def text(self) -> str:
        where = "above" if self.direction == "up" else "below"
        whose = {"key": "", "desk": "the desk's ", "mco": "MCO's "}[self.source]
        return (
            f"{self.coin} closed {where} {whose}{self.label} {_fmt(self.level)} "
            f"({_fmt(self.prev_close)} -> {_fmt(self.close)})"
        )


def _fmt(x: float) -> str:
    return f"{x:,.2f}" if x >= 100 else f"{x:.4g}"


def crossed(prev_close: float, close: float, level: float) -> Literal["up", "down"] | None:
    if prev_close < level <= close:
        return "up"
    if prev_close > level >= close:
        return "down"
    return None


@dataclass
class LevelWatchResult:
    day: dt.date
    run_id: int | None = None
    status: str = "running"
    crossings: list[Crossing] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    alerts: dict[str, str] = field(default_factory=dict)
    skipped: str | None = None
    error: str | None = None

    def summary(self, private: bool = False) -> str:
        lines = [
            f"Level watch for {self.day}: {self.status}"
            + (f" (run {self.run_id})" if self.run_id else "")
        ]
        if self.skipped:
            lines.append(f"Skipped: {self.skipped}")
        if self.error:
            lines.append(f"Error: {self.error}")
        lines += [f"Note: {s}" for s in self.stale]
        shown = [c for c in self.crossings if private or c.source != "mco"]
        hidden = len(self.crossings) - len(shown)
        lines.append(
            f"Crossings: {len(self.crossings)}"
            + (f" ({hidden} MCO-derived, hidden here)" if hidden else "")
        )
        lines += [f"- {c.text()}" for c in shown]
        if self.alerts:
            lines.append("Alerts: " + ", ".join(f"{k} {v}" for k, v in self.alerts.items()))
        return "\n".join(lines)


def find_crossings(session: Session, day: dt.date) -> tuple[list[Crossing], list[str]]:
    """(crossings, notes) for `day` across active coins."""
    from desk.analytics.levels import key_levels
    from desk.data import market
    from desk.data.coins import active_coins

    prev_day = day - dt.timedelta(days=1)
    week = day - dt.timedelta(days=day.weekday())
    out: list[Crossing] = []
    notes: list[str] = []
    for coin in active_coins(session):
        closes = dict(
            session.execute(
                select(CandleDaily.date, CandleDaily.close).where(
                    CandleDaily.coin == coin.symbol, CandleDaily.date.in_([prev_day, day])
                )
            ).all()
        )
        if day not in closes or prev_day not in closes:
            notes.append(f"{coin.symbol}: no candles for {prev_day} and {day}")
            continue
        prev_close, close = float(closes[prev_day]), float(closes[day])

        levels: list[tuple[str, float | None, str]] = []
        signals = session.scalars(
            select(Signal)
            .where(
                Signal.coin == coin.symbol, Signal.week == week, Signal.source.in_(LEVEL_SOURCES)
            )
            .order_by(Signal.version.desc(), Signal.id)
        )
        seen: set[str] = set()
        for sig in signals:
            if sig.source in seen:  # the newest signal version only
                continue
            seen.add(sig.source)
            levels += [(SIGNAL_LABELS[n], getattr(sig, n), sig.source) for n in SIGNAL_LEVELS]
        daily = market.load_daily(session, coin.symbol, prev_day)
        levels += [
            (KEY_LABELS.get(lv.name, lv.name), lv.value, "key")
            for lv in key_levels(daily, prev_day)
        ]
        for label, level, source in levels:
            direction = None if level is None else crossed(prev_close, close, level)
            if direction and level is not None:
                out.append(
                    Crossing(
                        coin.symbol, day, label, float(level), direction, prev_close, close, source
                    )
                )
    return out, notes


def already_ran(session: Session, day: dt.date) -> bool:
    """A successful run for `day` exists (each run checks the day before it started)."""
    start = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), dt.UTC)
    q = select(JobRun.id).where(
        JobRun.job == JOB,
        JobRun.status == "success",
        JobRun.started_at >= start,
        JobRun.started_at < start + dt.timedelta(days=1),
    )
    return session.scalar(q.limit(1)) is not None


def alert_for(day: dt.date, crossings: list[Crossing]) -> Alert:
    body = "\n".join(c.text() for c in crossings) + "\n\nCloses are UTC daily closes."
    return Alert("level_cross", f"Level crossings on {day}", body)


def run_levelwatch(
    sessions: sessionmaker[Session],
    now: dt.datetime | None = None,
    *,
    alerts: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> LevelWatchResult:
    now = now or dt.datetime.now(dt.UTC)
    day = now.date() - dt.timedelta(days=1)
    result = LevelWatchResult(day=day)
    with sessions() as session:
        if not force and not dry_run and already_ran(session, day):
            result.status, result.skipped = "success", f"already ran for {day}"
            return result
    if not dry_run:
        with sessions.begin() as session:
            row = JobRun(job=JOB, started_at=now)
            session.add(row)
            session.flush()
            result.run_id = row.id
    try:
        with sessions() as session:
            result.crossings, result.stale = find_crossings(session, day)
        if result.crossings and alerts and not dry_run:
            result.alerts = send(alert_for(day, result.crossings))
        result.status = "success"
    except Exception as exc:
        result.status, result.error = "failed", type(exc).__name__
    if result.run_id is not None:
        with sessions.begin() as session:
            row = session.get(JobRun, result.run_id)
            row.ended_at = dt.datetime.now(dt.UTC)
            row.status = result.status
            row.error = result.error
    return result
