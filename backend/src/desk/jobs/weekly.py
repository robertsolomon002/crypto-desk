"""Weekly job (GitHub Actions, Monday 00:15 UTC; Section 3.5, Stage 7.1, D51).

`signals.run` does steps 1 to 6 (refresh, resolve, desk, baselines, MCO, append). This job
then writes the brief (`agents.brief_writer`, stored in `briefs`), sends the `brief_ready`
alert, and records the run in `job_runs` with its server-key cost.

Status `failed` (CLI exit 1, and the workflow sends `ops_failure`) when a source failed, a coin
was stale, a desk run errored, was refused or stayed invalid, the brief failed, or something
unexpected happened. Rows already written stay written (append-only); a re-run fills gaps.

`dry_run`: no signals, outcomes, brief rows, alerts or `job_runs` row; the desk and the brief
writer still run (and cost money), so the report shows real signals, cost and wall time.
"""

import datetime as dt
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from desk.agents import brief_writer
from desk.config import load_app_settings
from desk.models import Brief, Coin, JobRun, LlmSpend
from desk.notify import Alert, send
from desk.signals.chain import Proposed
from desk.signals.run import Echo, SignalsRun, desk_state, run_signals

JOB = "weekly"
SPEND_SOURCES = ("desk", "brief")


@dataclass
class WeeklyResult:
    started: dt.datetime
    dry_run: bool
    run_id: int | None = None
    status: str = "running"
    signals: SignalsRun | None = None
    brief: brief_writer.BriefResult | None = None
    brief_id: int | None = None
    brief_note: str | None = None
    alerts: dict[str, str] = field(default_factory=dict)
    cost: Decimal = Decimal(0)
    seconds: float = 0.0
    error: str | None = None  # the exception type (the summary goes to a public log)
    error_detail: str | None = None  # the message too, for `job_runs` only

    @property
    def problems(self) -> list[str]:
        out = list(self.signals.problems) if self.signals else []
        if self.brief is None and self.brief_note:
            out.append(f"brief: {self.brief_note}")
        if self.error:
            out.append(f"error: {self.error}")
        return out

    def summary(self, private: bool = False) -> str:
        """The run report. MCO-derived rows are hidden unless `private` (Decision 6: the
        workflow log is public)."""
        s = self.signals
        head = "Weekly job (dry run)" if self.dry_run else "Weekly job"
        lines = [
            f"{head} {self.started:%Y-%m-%d %H:%M} UTC: {self.status} ({self.seconds:.0f} s, "
            f"server-key cost ${self.cost:.4f}" + (f", run {self.run_id})" if self.run_id else ")")
        ]
        if s:
            lines.append(
                f"Week {s.week} (data as of {s.as_of}), signal version v{s.version}, "
                f"coins {', '.join(s.coins) or '-'}"
                + (" (degraded: watchlist skipped)" if s.degraded else "")
            )
        if self.problems:
            lines += ["", "Problems:", *(f"- {p}" for p in self.problems)]
        if s and s.notes:
            lines += ["", "Notes:", *(f"- {n}" for n in s.notes)]
        if s:
            lines += ["", f"Resolved: {len(s.resolved)} signal(s)"]
            lines += [
                "",
                "Signals"
                + (" (not written)" if self.dry_run else f" ({len(s.written)} written)")
                + ":",
            ]
            for r in s.runs.values():
                lines.append(
                    f"- {r.coin}: desk {r.desk_status}"
                    + (f" in {r.desk_seconds:.0f} s" if r.desk_seconds else "")
                    + (f", snapshot {r.snapshot_id}" if r.snapshot_id else "")
                )
                lines += [
                    f"    {signal_line(p)}"
                    if private or p.source != "mco"
                    else "    mco      (hidden: MCO-derived)"
                    for p in r.signals
                ]
        if self.brief:
            b = self.brief
            lines += [
                "",
                f"Brief: {b.model}, {b.tokens_in} in / {b.tokens_out} out, "
                f"${b.cost:.4f}" + (f", id {self.brief_id}" if self.brief_id else ""),
            ]
            if private:  # model text that may cite MCO: never in the public log
                lines += ["", b.content]
        elif self.brief_note:
            lines += ["", f"Brief: none ({self.brief_note})"]
        if self.alerts:
            lines += ["", "Alerts: " + ", ".join(f"{k} {v}" for k, v in self.alerts.items())]
        return "\n".join(lines)


def _fmt(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:,.2f}" if x >= 100 else f"{x:.4g}"


def signal_line(p: Proposed) -> str:
    stance = "lean long" if p.stance == "lean_long" else "flat"
    out = f"{p.source:<8} {stance} {p.confidence:.2f}"
    if p.entry_low is not None and p.entry_high is not None:
        out += f", entry {_fmt(p.entry_low)}-{_fmt(p.entry_high)}"
    if p.invalidation is not None:
        out += f", invalidation {_fmt(p.invalidation)}"
    if p.target is not None:
        out += f", target {_fmt(p.target)}"
    return out


# --- Brief inputs ----------------------------------------------------------------------------


def _compact_desk(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {"status": "missing"}
    reports = {
        name: {k: r.get(k) for k in ("status", "summary", "findings", "note")}
        for name, r in (state.get("reports") or {}).items()
    }
    debate = {
        node: [{"text": p.get("text"), "cites": p.get("cites")} for p in c.get("points") or []]
        for node, c in (state.get("debate") or {}).items()
    }
    return {
        "status": state.get("status"),
        "reports": reports,
        "debate": debate,
        "signal": state.get("signal"),
        "validation": state.get("validation"),
    }


def brief_inputs(session: Session, s: SignalsRun) -> list[dict[str, Any]]:
    from desk.analytics.levels import key_levels
    from desk.data import market

    coins = []
    for coin, r in s.runs.items():
        name = session.scalar(select(Coin.name).where(Coin.symbol == coin))
        levels = key_levels(market.load_daily(session, coin, s.as_of), s.as_of)
        coins.append(
            {
                "coin": coin,
                "name": name,
                "last_close": r.reference_close,
                "last_close_date": s.as_of.isoformat(),
                "signals": [
                    {k: v for k, v in asdict(p).items() if k not in ("coin", "transcript_ref")}
                    for p in r.signals
                ],
                "desk": _compact_desk(desk_state(session, r.snapshot_id)),
                "key_levels": [{"name": lv.name, "value": round(lv.value, 6)} for lv in levels],
            }
        )
    return coins


def brief_alert(week: dt.date, result: brief_writer.BriefResult, s: SignalsRun) -> Alert:
    lines = list(result.brief.summary)
    lines.append("")
    for r in s.runs.values():
        desk = next((p for p in r.signals if p.source == "desk"), None)
        if desk is None:
            lines.append(f"{r.coin}: desk {r.desk_status}")
        else:
            lines.append(f"{r.coin}: {signal_line(desk).removeprefix('desk').strip()}")
    lines += ["", "Not financial advice."]
    url = (load_app_settings().get("app") or {}).get("url")
    return Alert("brief_ready", f"Weekly brief: week of {week}", "\n".join(lines), url)


# --- The job ---------------------------------------------------------------------------------


def _spend_since(session: Session, since: dt.datetime) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(LlmSpend.cost), 0)).where(
            LlmSpend.created_at >= since, LlmSpend.source.in_(SPEND_SOURCES)
        )
    )
    return Decimal(total or 0)


async def run_weekly(
    sessions: sessionmaker[Session],
    now: dt.datetime | None = None,
    *,
    dry_run: bool = False,
    refresh: bool = True,
    alerts: bool = True,
    echo: Echo = lambda line, err: None,
    **signal_kwargs: Any,
) -> WeeklyResult:
    now = now or dt.datetime.now(dt.UTC)
    clock = time.monotonic()
    with sessions() as session:
        db_now = session.scalar(select(func.now()))
    result = WeeklyResult(started=now, dry_run=dry_run)
    if not dry_run:
        with sessions.begin() as session:
            row = JobRun(job=JOB, started_at=now)
            session.add(row)
            session.flush()
            result.run_id = row.id
    try:
        s = await run_signals(
            sessions, now, dry_run=dry_run, refresh=refresh, echo=echo, **signal_kwargs
        )
        result.signals = s
        with sessions() as session:
            existing = session.scalar(select(Brief.id).where(Brief.week == s.week).limit(1))
        if not s.runs:
            result.brief_note = "no coins to write about"
        elif existing is not None and not dry_run:
            result.brief_id, result.brief_note = existing, "already written for this week"
        else:
            echo("brief ...", False)
            try:
                with sessions() as session:
                    inputs = brief_inputs(session, s)
                    result.brief = await brief_writer.write(
                        session, week=s.week, as_of=s.as_of, coins=inputs
                    )
            except brief_writer.BriefError as e:
                result.brief_note = str(e)
            except Exception as e:  # provider errors after retries
                result.brief_note = f"{type(e).__name__}"
            if result.brief is not None and not dry_run:
                b = result.brief
                with sessions.begin() as session:
                    row = Brief(
                        week=s.week,
                        model=b.model,
                        prompt_version=brief_writer.PROMPT_VERSION,
                        content=b.content,
                        payload=b.brief.model_dump(),
                    )
                    session.add(row)
                    session.flush()
                    result.brief_id = row.id
                if alerts:
                    result.alerts = send(brief_alert(s.week, b, s))
    except Exception as exc:
        result.error = type(exc).__name__
        result.error_detail = f"{type(exc).__name__}: {exc}"[:1000]
    with sessions() as session:
        result.cost = _spend_since(session, db_now)
    result.status = "failed" if result.problems else "success"
    result.seconds = time.monotonic() - clock
    if result.run_id is not None:
        with sessions.begin() as session:
            row = session.get(JobRun, result.run_id)
            row.ended_at = dt.datetime.now(dt.UTC)
            row.status = result.status
            row.cost = result.cost
            extra = [result.error_detail] if result.error_detail else []
            row.error = "\n".join(result.problems + extra) or None
    return result
