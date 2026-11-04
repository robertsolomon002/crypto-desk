"""The Health report (Stage 8.1, D53): what the admin Health page shows and what the weekly ops
summary condenses.

- **Jobs:** the last run of each scheduled job, its last success, whether it is overdue (no
  success within `ops.jobs.<job>` hours) and its failures in the error window.
- **Freshness:** the newest date per source, per coin for prices and on-chain data.
- **Spend:** server-key LLM spend this month against the Decision 9 cap, the projected month
  end, and which degradations are on.
- **Errors:** `app_errors` counts, failed job runs and failed MCO videos in the window.
- **Usage:** database size against Neon Free's storage limit and the largest tables. Cloud Run
  and Neon compute have no free API we can call without new credentials, so they are links.

Admin only. Nothing here carries MCO-derived text: MCO appears as counts and dates.
"""

import calendar
import datetime as dt
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from desk.agents import cost
from desk.config import get_settings, load_app_settings
from desk.data import sentiment
from desk.data.coins import active_coins
from desk.models import (
    Brief,
    CandleDaily,
    JobRun,
    LlmSpend,
    McoVideo,
    News,
    SeriesPoint,
    Signal,
)
from desk.ops import errors, ops_settings

ONCHAIN_COINS = ("BTC", "ETH")  # Coin Metrics community coverage (Section 3.1)

DEGRADATIONS = {  # Decision 9, in `budget.degrade_order`
    "chat_model": "Rob's own chat uses the cheaper model",
    "mco_low_priority": "MCO summaries skip lower-priority videos",
    "brief_writer_haiku": "The weekly brief writer uses Haiku instead of Sonnet",
}

# Checked 2026-11-04 (D53). Free-tier numbers are for reading the console pages, not enforced.
LINKS = [
    ("Cloud Run metrics (requests, instances, memory)",
     "https://console.cloud.google.com/run/detail/us-central1/desk-api/metrics?project=crypto-desk-513023"),
    ("Cloud Run logs and errors",
     "https://console.cloud.google.com/run/detail/us-central1/desk-api/logs?project=crypto-desk-513023"),
    ("Error Reporting",
     "https://console.cloud.google.com/errors?project=crypto-desk-513023"),
    ("GCP billing (the $1 budget alert)",
     "https://console.cloud.google.com/billing/linkedaccount?project=crypto-desk-513023"),
    ("Neon usage (compute hours, storage)", "https://console.neon.tech/app/projects"),
    ("Backups bucket",
     "https://console.cloud.google.com/storage/browser/crypto-desk-513023-backups?project=crypto-desk-513023"),
    ("GitHub Actions runs", "https://github.com/robertsolomon002/crypto-desk/actions"),
]  # fmt: skip
FREE_TIER = [
    "Cloud Run: 2 million requests, 180,000 vCPU-seconds and 360,000 GiB-seconds a month",
    "Neon Free: 100 CU-hours a month per project, 1 GB storage, 6 hours of restore history",
    "Cloud Storage: 5 GB-months in us-central1, 5,000 Class A operations a month",
]


class JobHealth(BaseModel):
    job: str
    last_status: str | None  # running | success | failed | None (never ran)
    last_started_at: dt.datetime | None
    last_ended_at: dt.datetime | None
    last_seconds: float | None
    last_success_at: dt.datetime | None
    max_age_hours: int
    overdue: bool  # no success within max_age_hours
    runs: int  # in the error window
    failures: int  # in the error window
    last_error: str | None  # the newest failed run's error, cut to 300 characters


class SourceFreshness(BaseModel):
    source: str
    detail: str
    last_date: dt.date | None
    age_days: int | None
    max_age_days: int
    stale: bool


class SpendSource(BaseModel):
    source: str
    cost: float


class Degradation(BaseModel):
    step: str
    label: str
    active: bool


class SpendHealth(BaseModel):
    month: str  # YYYY-MM, UTC
    spent_usd: float
    cap_usd: float
    degrade_at_usd: float
    projected_usd: float  # this month's pace carried to the month end
    degraded: bool
    exhausted: bool  # server-key runs are refused
    by_source: list[SpendSource]
    degradations: list[Degradation]


class ErrorCount(BaseModel):
    where: str
    kind: str
    count: int
    last_at: dt.datetime


class ErrorHealth(BaseModel):
    window_days: int
    total: int  # app errors + failed job runs + failed MCO videos
    app: list[ErrorCount]
    job_failures: int
    mco_failures: int


class TableSize(BaseModel):
    table: str
    bytes: int


class Link(BaseModel):
    label: str
    url: str


class UsageHealth(BaseModel):
    database_bytes: int
    storage_limit_bytes: int
    tables: list[TableSize]  # the largest
    links: list[Link]
    free_tier: list[str]


class HealthReport(BaseModel):
    generated_at: dt.datetime
    ok: bool  # no overdue job, no stale source, budget not exhausted
    problems: list[str]
    jobs: list[JobHealth]
    freshness: list[SourceFreshness]
    spend: SpendHealth
    errors: ErrorHealth
    usage: UsageHealth


def _mco_on() -> bool:
    flags = load_app_settings().get("features") or {}
    return bool(flags.get("mco", True)) and get_settings().mco_enabled


def job_health(session: Session, now: dt.datetime, window: dt.timedelta) -> list[JobHealth]:
    expected: dict[str, int] = (ops_settings().get("jobs") or {}).copy()
    if not _mco_on():
        expected.pop("mco", None)
    since = now - window
    out = []
    for job, hours in expected.items():
        last = session.scalars(
            select(JobRun).where(JobRun.job == job).order_by(JobRun.started_at.desc()).limit(1)
        ).first()
        success = session.scalar(
            select(func.max(JobRun.started_at)).where(JobRun.job == job,
                                                      JobRun.status == "success")
        )  # fmt: skip
        runs, failures = session.execute(
            select(func.count(), func.count().filter(JobRun.status == "failed"))
            .where(JobRun.job == job, JobRun.started_at >= since)
        ).one()  # fmt: skip
        failed = session.scalars(
            select(JobRun.error).where(JobRun.job == job, JobRun.status == "failed")
            .order_by(JobRun.started_at.desc()).limit(1)
        ).first()  # fmt: skip
        seconds = None
        if last is not None and last.ended_at is not None:
            seconds = round((last.ended_at - last.started_at).total_seconds(), 1)
        out.append(
            JobHealth(
                job=job,
                last_status=last.status if last else None,
                last_started_at=last.started_at if last else None,
                last_ended_at=last.ended_at if last else None,
                last_seconds=seconds,
                last_success_at=success,
                max_age_hours=int(hours),
                overdue=success is None or now - success > dt.timedelta(hours=int(hours)),
                runs=int(runs),
                failures=int(failures),
                last_error=failed[:300] if failed else None,
            )
        )
    return out


def _row(source: str, detail: str, last: dt.date | None, today: dt.date,
         max_age: int) -> SourceFreshness:  # fmt: skip
    age = (today - last).days if last is not None else None
    return SourceFreshness(source=source, detail=detail, last_date=last, age_days=age,
                           max_age_days=max_age, stale=age is None or age > max_age)  # fmt: skip


def _series_last(session: Session, prefix: str) -> dt.date | None:
    match = SeriesPoint.key.startswith(prefix) if prefix.endswith(":") else (
        SeriesPoint.key == prefix)  # fmt: skip
    return session.scalar(select(func.max(SeriesPoint.date)).where(match))


def freshness(session: Session, today: dt.date) -> list[SourceFreshness]:
    rows = []
    for coin in active_coins(session):
        last = session.scalar(
            select(func.max(CandleDaily.date)).where(CandleDaily.coin == coin.symbol)
        )
        rows.append(_row("Prices", f"{coin.symbol} daily candles", last, today, 2))
    for coin in ONCHAIN_COINS:  # on-chain values can be a day behind at 00:20 UTC (D36)
        last = _series_last(session, f"cm:{coin}:")
        rows.append(_row("On-chain", f"{coin} Coin Metrics", last, today, 3))
    rows.append(_row("Fear & Greed", "alternative.me", _series_last(session, sentiment.KEY),
                     today, 2))  # fmt: skip
    rows.append(_row("Dominance", "CoinGecko snapshot", _series_last(session, "dominance:"),
                     today, 2))  # fmt: skip
    # FRED dates observations by period and releases them late (D32): stale after two months.
    rows.append(_row("FRED macro", "newest observation", _series_last(session, "fred:"),
                     today, 62))  # fmt: skip
    newest = session.scalar(select(func.max(News.published_at)))
    rows.append(_row("Headlines", "RSS feeds", newest.date() if newest else None, today, 2))
    if _mco_on():  # a date and a count only (Decision 6)
        processed = session.scalar(
            select(func.max(McoVideo.processed_at)).where(McoVideo.status == "done")
        )
        rows.append(_row("MCO", "newest summarized video", processed.date() if processed
                         else None, today, 7))  # fmt: skip
    week = session.scalar(select(func.max(Signal.week)).where(Signal.source == "desk"))
    rows.append(_row("Signals", "newest desk signal week", week, today, 8))
    brief = session.scalar(select(func.max(Brief.week)))
    rows.append(_row("Brief", "newest weekly brief", brief, today, 8))
    return rows


def spend(session: Session, today: dt.date) -> SpendHealth:
    b = cost.budget(session, today)
    start = cost.month_start(today)
    total = func.sum(LlmSpend.cost)
    by_source = [
        SpendSource(source=s, cost=float(c or 0))
        for s, c in session.execute(
            select(LlmSpend.source, total).where(LlmSpend.date >= start)
            .group_by(LlmSpend.source).order_by(total.desc())
        )
    ]  # fmt: skip
    days = calendar.monthrange(today.year, today.month)[1]
    projected = b.spent / Decimal(today.day) * Decimal(days)
    order = (load_app_settings().get("budget") or {}).get("degrade_order") or list(DEGRADATIONS)
    return SpendHealth(
        month=start.strftime("%Y-%m"),
        spent_usd=round(float(b.spent), 6),
        cap_usd=float(b.cap),
        degrade_at_usd=float(b.degrade_at),
        projected_usd=round(float(projected), 4),
        degraded=b.degraded,
        exhausted=b.exhausted,
        by_source=by_source,
        degradations=[
            Degradation(step=s, label=DEGRADATIONS.get(s, s), active=b.degraded) for s in order
        ],  # fmt: skip
    )


def error_health(session: Session, now: dt.datetime, window_days: int) -> ErrorHealth:
    since = now - dt.timedelta(days=window_days)
    app = [ErrorCount(where=w, kind=k, count=c, last_at=last)
           for w, k, c, last in errors.counts(session, since)]  # fmt: skip
    jobs = session.scalar(
        select(func.count()).select_from(JobRun)
        .where(JobRun.status == "failed", JobRun.started_at >= since)
    ) or 0  # fmt: skip
    mco = 0
    if _mco_on():
        mco = session.scalar(
            select(func.count()).select_from(McoVideo)
            .where(McoVideo.status == "failed", McoVideo.published_at >= since)
        ) or 0  # fmt: skip
    return ErrorHealth(window_days=window_days, total=sum(e.count for e in app) + jobs + mco,
                       app=app, job_failures=jobs, mco_failures=mco)  # fmt: skip


TABLE_SIZES = text(
    "SELECT c.relname, pg_total_relation_size(c.oid) FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relkind = 'r' "
    "ORDER BY 2 DESC LIMIT :n"
)


def usage(session: Session, top: int = 8) -> UsageHealth:
    size = session.scalar(text("SELECT pg_database_size(current_database())")) or 0
    limit_gb = float(ops_settings().get("neon_storage_limit_gb", 1))
    tables = [TableSize(table=t, bytes=int(b)) for t, b in session.execute(TABLE_SIZES,
                                                                           {"n": top})]  # fmt: skip
    return UsageHealth(
        database_bytes=int(size),
        storage_limit_bytes=int(limit_gb * 1024**3),
        tables=tables,
        links=[Link(label=label, url=url) for label, url in LINKS],
        free_tier=FREE_TIER,
    )


def report(session: Session, now: dt.datetime | None = None) -> HealthReport:
    now = now or dt.datetime.now(dt.UTC)
    window = int(ops_settings().get("error_window_days", 7))
    jobs = job_health(session, now, dt.timedelta(days=window))
    fresh = freshness(session, now.date())
    money = spend(session, now.date())
    use = usage(session)
    problems = [f"{j.job}: no successful run in {j.max_age_hours} h" for j in jobs if j.overdue]
    problems += [f"{f.source} ({f.detail}): last {f.last_date or 'never'}"
                 for f in fresh if f.stale]  # fmt: skip
    if money.exhausted:
        problems.append(f"server LLM spend ${money.spent_usd:.2f} reached the cap")
    if use.database_bytes > 0.8 * use.storage_limit_bytes:
        problems.append(f"database at {use.database_bytes / use.storage_limit_bytes:.0%} of "
                        "Neon's storage limit")  # fmt: skip
    return HealthReport(generated_at=now, ok=not problems, problems=problems, jobs=jobs,
                        freshness=fresh, spend=money,
                        errors=error_health(session, now, window), usage=use)  # fmt: skip
