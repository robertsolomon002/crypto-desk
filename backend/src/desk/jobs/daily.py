"""Daily job (GitHub Actions, 00:20 UTC): refresh every source, check candle freshness, refresh
the analytics cache, and record the run in `job_runs`.

The run fails (status `failed`, CLI exit 1) if any source fails, any active coin's last candle
is older than yesterday (UTC), or an unexpected error occurs. The workflow then sends an
`ops_failure` alert with the summary and the run link (admin channels only). Lagging context
series (on-chain data can be a day behind at 00:20 UTC) are reported as notes, not failures.
"""

import datetime as dt
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from desk.data.update import SourceResult, update_all
from desk.models import CandleDaily, JobRun, SeriesPoint

JOB = "daily"
NOTE_AGE_DAYS = {"fng": 1, "cm:": 2}  # key prefix -> max age before a note


@dataclass
class DailyResult:
    run_id: int
    started: dt.datetime
    status: str = "running"
    sources: dict[str, SourceResult] = field(default_factory=dict)
    stale: list[str] = field(default_factory=list)  # failures: coins without yesterday's candle
    notes: list[str] = field(default_factory=list)  # lagging context series, not failures
    cache: dict[str, int] | None = None
    error: str | None = None
    seconds: float = 0.0

    @property
    def problems(self) -> list[str]:
        out = [f"{r.name} FAILED: {r.error}" for r in self.sources.values() if not r.ok]
        out += [f"stale: {s}" for s in self.stale]
        if self.error:
            out.append(f"error: {self.error}")
        return out

    def summary(self) -> str:
        lines = [f"Daily job {self.started:%Y-%m-%d %H:%M} UTC: {self.status} "
                 f"({self.seconds:.0f} s, run {self.run_id})"]  # fmt: skip
        if self.problems:
            lines += ["", "Problems:", *(f"- {p}" for p in self.problems)]
        if self.notes:
            lines += ["", "Notes:", *(f"- {n}" for n in self.notes)]
        lines += ["", "Sources:"]
        for r in self.sources.values():
            state = "FAILED" if not r.ok else ("skipped" if r.skipped else "ok")
            lines.append(f"- {r.name}: {state}; {'; '.join(r.lines) or '-'}")
        if self.cache is not None:
            counts = ", ".join(f"{k} {v}" for k, v in self.cache.items())
            lines.append(f"- analytics cache: {counts}")
        return "\n".join(lines)


def check_freshness(session: Session, today: dt.date) -> tuple[list[str], list[str]]:
    """(stale coins, notes): every active coin needs a candle for yesterday (UTC)."""
    from desk.data.coins import active_coins

    yesterday = today - dt.timedelta(days=1)
    stale = []
    for c in active_coins(session):
        last = session.scalar(
            select(func.max(CandleDaily.date)).where(CandleDaily.coin == c.symbol)
        )
        if last is None or last < yesterday:
            stale.append(f"{c.symbol} last candle {last or 'none'} (expected {yesterday})")
    notes = []
    for key, last in session.execute(
        select(SeriesPoint.key, func.max(SeriesPoint.date)).group_by(SeriesPoint.key)
    ):
        limit = next((v for p, v in NOTE_AGE_DAYS.items() if key.startswith(p)), None)
        if limit is not None and (today - last).days > limit and not key.endswith("HashRate"):
            notes.append(f"{key} last value {last} ({(today - last).days} days old)")
    return stale, sorted(notes)


def run_daily(
    sessions: sessionmaker[Session],
    now: dt.datetime | None = None,
    refresh_cache: bool = True,
    update: Callable[..., dict[str, SourceResult]] | None = None,  # default: update_all
    echo: Callable[[str, bool], None] = lambda line, err: None,
) -> DailyResult:
    from desk.analytics import cache

    now = now or dt.datetime.now(dt.UTC)
    clock = time.monotonic()
    with sessions.begin() as session:
        run = JobRun(job=JOB, started_at=now)
        session.add(run)
        session.flush()
        result = DailyResult(run.id, now)
    try:
        result.sources = (update or update_all)(sessions, now, echo=echo)
        with sessions() as session:
            result.stale, result.notes = check_freshness(session, now.date())
        if refresh_cache:
            echo("analytics cache:", False)
            with sessions.begin() as session:
                result.cache = cache.refresh(session)
            echo("  " + ", ".join(f"{k} {v}" for k, v in result.cache.items()), False)
    except Exception as exc:  # recorded and reported; the workflow alerts on the exit code
        result.error = f"{type(exc).__name__}: {exc}"
    result.status = "failed" if result.problems else "success"
    result.seconds = time.monotonic() - clock
    with sessions.begin() as session:
        row = session.get(JobRun, result.run_id)
        row.ended_at = dt.datetime.now(dt.UTC)
        row.status = result.status
        row.error = "\n".join(result.problems) or None
    return result
