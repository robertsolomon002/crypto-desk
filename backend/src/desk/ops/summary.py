"""The weekly ops summary to the admin Telegram (Stage 8.1, D53): the Health report in a few
lines. Counts and dates only, no MCO-derived text, so it is safe in the workflow log too."""

import datetime as dt

from desk.ops.health import HealthReport


def _ago(at: dt.datetime | None, now: dt.datetime) -> str:
    if at is None:
        return "never"
    hours = (now - at).total_seconds() / 3600
    return f"{hours:.0f} h ago" if hours < 48 else f"{hours / 24:.0f} d ago"


def _mb(n: int) -> str:
    return f"{n / 1024**2:.1f} MB"


def format_summary(r: HealthReport) -> tuple[str, str]:
    """(title, body) for the `ops_summary` alert."""
    now = r.generated_at
    title = "Weekly ops: all good" if r.ok else f"Weekly ops: {len(r.problems)} to look at"
    lines: list[str] = []
    if r.problems:
        lines += ["Problems:", *(f"- {p}" for p in r.problems), ""]
    lines.append("Jobs (last run; runs and failures in the last "
                 f"{r.errors.window_days} days):")  # fmt: skip
    for j in r.jobs:
        flag = " OVERDUE" if j.overdue else ""
        if j.last_status is None:
            lines.append(f"- {j.job}: never ran{flag}")
            continue
        lines.append(f"- {j.job}: {j.last_status} {_ago(j.last_started_at, now)}; "
                     f"{j.runs} runs, {j.failures} failed{flag}")  # fmt: skip
    stale = [f for f in r.freshness if f.stale]
    lines += ["", f"Data: {len(r.freshness) - len(stale)} of {len(r.freshness)} sources fresh"]
    s = r.spend
    lines += [
        "",
        f"LLM spend {s.month}: ${s.spent_usd:.2f} of ${s.cap_usd:.2f} "
        f"(pace ${s.projected_usd:.2f} by month end)"
        + ("; DEGRADED" if s.degraded else "") + ("; CAP REACHED" if s.exhausted else ""),
    ]  # fmt: skip
    e = r.errors
    lines.append(f"Errors ({e.window_days} days): {e.total} "
                 f"({sum(c.count for c in e.app)} app, {e.job_failures} job runs, "
                 f"{e.mco_failures} MCO videos)")  # fmt: skip
    for c in e.app[:5]:
        lines.append(f"- {c.where} {c.kind}: {c.count}")
    u = r.usage
    lines.append(f"Database: {_mb(u.database_bytes)} of {_mb(u.storage_limit_bytes)}")
    return title, "\n".join(lines)
