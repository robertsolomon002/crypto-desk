"""MCO daily job (GitHub Actions, 06:30 UTC; Section 3.4, D48): discover, summarize, snap,
alert, and record the run in `job_runs`.

Privacy (Decision 6): MCO-derived text (titles, descriptions, summaries, scenarios, biases)
goes only to the database and to the alert channels Decision 11 routes it to. The job summary,
which is printed in the public Actions log and sent with ops alerts, holds only video ids,
statuses, counts, model ids and short error codes.

Status `failed` (CLI exit 1) when discovery found no listing at all, a video's extraction
failed outright, or an unexpected error happened. A low-detail fallback is a success.
"""

import datetime as dt
import logging
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from desk.config import get_settings, load_app_settings
from desk.mco import discover as disc
from desk.mco import snap as snapper
from desk.mco import summarize as summ
from desk.models import Coin, JobRun, McoExtract, McoVideo, McoWaveLabel

log = logging.getLogger(__name__)

JOB = "mco"


@dataclass
class VideoOutcome:
    video_id: str
    status: str  # done | failed
    model: str | None = None
    low_detail: bool = False
    coins: int = 0
    labels: int = 0
    matched: int = 0
    calls: int = 0
    error: str | None = None  # short code


@dataclass
class McoResult:
    run_id: int | None
    started: dt.datetime
    status: str = "running"
    discovered: disc.DiscoverResult | None = None
    videos: list[VideoOutcome] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    alerts: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    seconds: float = 0.0

    @property
    def problems(self) -> list[str]:
        out = []
        d = self.discovered
        if d is not None and d.source == "none":
            out.append(f"discovery found no listing ({', '.join(d.errors) or 'no videos'})")
        out += [f"{v.video_id} failed: {v.error}" for v in self.videos if v.status == "failed"]
        if self.error:
            out.append(f"error: {self.error}")
        return out

    def summary(self) -> str:
        """Ids, counts and codes only: this text is public in the Actions log."""
        lines = [
            f"MCO job {self.started:%Y-%m-%d %H:%M} UTC: {self.status} "
            f"({self.seconds:.0f} s, run {self.run_id})"
        ]
        if self.problems:
            lines += ["", "Problems:", *(f"- {p}" for p in self.problems)]
        if self.notes:
            lines += ["", "Notes:", *(f"- {n}" for n in self.notes)]
        d = self.discovered
        if d is not None:
            skipped = ", ".join(f"{k} {v}" for k, v in sorted(d.skipped.items())) or "-"
            lines += [
                "",
                f"Discovery: source {d.source}, {d.seen} listed, {len(d.new)} new, "
                f"{len(d.deferred)} live/upcoming; skipped: {skipped}",
            ]
            if d.errors:
                lines.append(f"- listing errors: {', '.join(d.errors)}")
        if self.videos:
            lines += ["", "Videos:"]
            for v in self.videos:
                if v.status == "done":
                    detail = " (low detail)" if v.low_detail else ""
                    lines.append(
                        f"- {v.video_id}: done on {v.model}{detail}; {v.coins} coins, "
                        f"{v.matched}/{v.labels} labels snapped, {v.calls} calls"
                    )
                else:
                    lines.append(f"- {v.video_id}: failed ({v.error})")
        if self.alerts:
            lines += ["", "Alerts: " + ", ".join(f"{k} {v}" for k, v in self.alerts.items())]
        return "\n".join(lines)


def enabled() -> bool:
    flags = load_app_settings().get("features") or {}
    return bool(flags.get("mco")) and get_settings().mco_enabled


# --- Per-video steps --------------------------------------------------------------------------


def alias_map(session: Session) -> dict[str, str]:
    """Upper-case alias or symbol -> symbol, from the `coins` table."""
    out: dict[str, str] = {}
    for symbol, aliases in session.execute(select(Coin.symbol, Coin.aliases)):
        out[symbol.upper()] = symbol
        for a in aliases or []:
            out[a.upper()] = symbol
    return out


def bars_for(session: Session, coin: str, as_of: dt.date, timeframe: str):
    from desk.data import market

    daily = market.load_daily(session, coin, as_of)
    if timeframe == "1w":  # include the open week: he labels the current swing too
        return market.resample_weekly(daily, include_partial=True)
    return daily


def last_closes(session: Session, coins: list[str], as_of: dt.date) -> dict[str, float]:
    out = {}
    for c in coins:
        daily = bars_for(session, c, as_of, "1d")
        if not daily.empty:
            out[c] = float(daily["close"].iloc[-1])
    return out


def snap_labels(
    session: Session, extract_id: int, payload: dict, as_of: dt.date
) -> tuple[int, int]:
    """Write one `pending` row per pivot label; returns (labels, matched)."""
    from desk.analytics import pivots as pv

    known = set(session.scalars(select(Coin.symbol)))
    cache: dict[tuple[str, str], tuple[list, list]] = {}
    labels = matched = 0
    for view in payload.get("coins", []):
        coin = view["coin"]
        if coin not in known:  # the FK needs a tracked coin; the labels stay in the payload
            continue
        for lab in view.get("pivot_labels", []):
            labels += 1
            tf = snapper.snap_timeframe(lab.get("chart_timeframe"))
            approx = dt.date.fromisoformat(lab["approx_date"])
            if (coin, tf) not in cache:
                bars = bars_for(session, coin, as_of, tf)
                cache[(coin, tf)] = (
                    pv.zigzag(bars, None, **pv.DEFAULTS[tf]),
                    [ts.date() for ts in bars.index],
                )
            pivots, dates = cache[(coin, tf)]
            result = snapper.snap_label(
                pivots, dates, lab.get("pivot_kind"), approx, float(lab["approx_price"]), tf
            )
            matched += result.pivot is not None
            session.add(
                McoWaveLabel(
                    extract_id=extract_id,
                    coin=coin,
                    label=str(lab["wave_label"])[:16],
                    timeframe=tf,
                    approx_date=approx,
                    approx_price=float(lab["approx_price"]),
                    pivot_kind=lab.get("pivot_kind"),
                    pivot_date=result.pivot.date if result.pivot else None,
                    pivot_price=result.pivot.price if result.pivot else None,
                    snap_bars=result.bars,
                    snap_pct=result.pct,
                    match_note=result.note,
                    status="pending",
                )
            )
    return labels, matched


def process_video(
    sessions: sessionmaker[Session], client: summ.Gemini, video_id: str, now: dt.datetime
) -> VideoOutcome:
    from desk.agents import cost

    with sessions() as session:
        v = session.get(McoVideo, video_id)
        as_of = v.published_at.date() - dt.timedelta(days=1)  # the last closed bar
        aliases = alias_map(session)
        closes = last_closes(session, sorted(set(aliases.values())), as_of)
        url, title, desc, published = v.url, v.title, v.description or "", v.published_at

    def spend(model: str, tin: int, tout: int) -> None:
        with sessions() as s:
            cost.record(s, "mco", model, tin, tout)

    out = VideoOutcome(video_id, "failed")
    try:
        result = summ.summarize(client, url, title, desc, published.date(), spend, aliases, closes)
    except summ.SummarizeFailed as exc:
        out.error = exc.code[:64]
        with sessions.begin() as session:
            v = session.get(McoVideo, video_id)
            v.status, v.error, v.processed_at = "failed", out.error, now
            v.attempts = (v.attempts or 0) + 1
        return out

    payload = summ.to_payload(result.extract)
    with sessions.begin() as session:
        row = McoExtract(
            video_id=video_id,
            model=result.model,
            prompt_version=summ.PROMPT_VERSION,
            payload=payload,
            summary=result.extract.summary,
        )
        session.add(row)
        session.flush()
        out.labels, out.matched = snap_labels(session, row.id, payload, as_of)
        v = session.get(McoVideo, video_id)
        v.status, v.low_detail, v.processed_at, v.error = "done", result.low_detail, now, None
        v.attempts = (v.attempts or 0) + 1
    out.status, out.model, out.low_detail = "done", result.model, result.low_detail
    out.coins, out.calls = len(payload.get("coins", [])), result.calls
    return out


# --- Alerts -----------------------------------------------------------------------------------


def video_alert(session: Session, video_id: str):
    """`new_mco_summary`: title, per-coin bias and the link (Decision 11)."""
    from desk.notify import Alert

    v = session.get(McoVideo, video_id)
    ex = session.scalars(
        select(McoExtract)
        .where(McoExtract.video_id == video_id)
        .order_by(McoExtract.id.desc())
        .limit(1)
    ).first()
    coins = (ex.payload or {}).get("coins", []) if ex else []
    chips = " · ".join(f"{c['coin']} {c['bias']}" for c in coins) or "no coins named"
    note = "\nLow detail: from the title and description only." if v.low_detail else ""
    body = f"{chips}{note}\nAI-extracted from the video; always check the video itself."
    return Alert("new_mco_summary", f"New MCO video: {v.title}", body, v.url)


# --- The job ----------------------------------------------------------------------------------


def run_mco(
    sessions: sessionmaker[Session],
    now: dt.datetime | None = None,
    gemini: Callable[[], summ.Gemini] | None = None,
    http: httpx.Client | None = None,
    notify: Callable | None = None,
    limit: int | None = None,
    video_ids: list[str] | None = None,
    alerts: bool = True,
) -> McoResult:
    from desk.agents import cost
    from desk.notify import Alert, send

    now = now or dt.datetime.now(dt.UTC)
    clock = time.monotonic()
    if not enabled():
        r = McoResult(None, now, status="disabled")
        r.notes.append("MCO is switched off (features.mco or MCO_ENABLED)")
        return r
    notify = notify or send
    settings = get_settings()
    with sessions.begin() as session:
        run = JobRun(job=JOB, started_at=now)
        session.add(run)
        session.flush()
        result = McoResult(run.id, now)
    own_http = http is None
    http = http or httpx.Client(timeout=httpx.Timeout(30.0))
    yt_key = settings.youtube_api_key.get_secret_value() if settings.youtube_api_key else None
    try:
        with sessions() as session:
            if video_ids:
                ids = [vid for vid in video_ids if session.get(McoVideo, vid) is not None]
                missing = sorted(set(video_ids) - set(ids))
                if missing:
                    result.notes.append(f"not discovered yet: {', '.join(missing)}")
            else:
                result.discovered = disc.discover(session, http, now, yt_key)
                b = cost.budget(session)
                if b.exhausted:
                    result.notes.append("server LLM cap reached: nothing summarized today")
                    ids = []
                else:
                    if b.degraded:
                        result.notes.append("near the cap: fewer videos, core coins only (D9)")
                    ids = disc.queue(session, now, degraded=b.degraded, limit=limit)
        if limit is not None:
            ids = ids[:limit]
        if ids:
            client = gemini() if gemini else _default_gemini()
            for vid in ids:
                result.videos.append(process_video(sessions, client, vid, now))
        if alerts:
            with sessions() as session:
                for v in result.videos:
                    if v.status == "done":
                        status = notify(video_alert(session, v.video_id))
                        _tally(result.alerts, "new_mco_summary", status)
            labels = sum(v.labels for v in result.videos if v.status == "done")
            matched = sum(v.matched for v in result.videos if v.status == "done")
            if labels:
                n = sum(1 for v in result.videos if v.labels)
                body = (
                    f"{labels} new wave labels from {n} video(s) await review "
                    f"({labels - matched} unmatched)."
                )
                status = notify(Alert("mco_review_pending", "MCO labels to review", body))
                _tally(result.alerts, "mco_review_pending", status)
    except Exception as exc:  # recorded and reported; the workflow alerts on the exit code
        # Type and code locations only: exception messages can quote extracted text.
        where = " < ".join(
            f"{f.name}:{f.lineno}" for f in reversed(traceback.extract_tb(exc.__traceback__)[-3:])
        )
        result.error = f"{type(exc).__name__} at {where}"
        log.error("mco job: unexpected %s", result.error)
    finally:
        if own_http:
            http.close()
    result.status = "failed" if result.problems else "success"
    result.seconds = time.monotonic() - clock
    with sessions.begin() as session:
        row = session.get(JobRun, result.run_id)
        row.ended_at = dt.datetime.now(dt.UTC)
        row.status = result.status
        row.error = "\n".join(result.problems) or None
    return result


def _default_gemini() -> summ.Gemini:
    s = get_settings()
    if s.google_api_key is None:
        raise RuntimeError("GOOGLE_API_KEY not set")
    cfg = load_app_settings().get("mco") or {}
    return summ.GenaiClient(
        s.google_api_key.get_secret_value(),
        int(cfg.get("gemini_timeout_seconds", 300)),
        int(cfg.get("gemini_attempts", 3)),
    )


def _tally(alerts: dict[str, str], event: str, status: dict[str, str]) -> None:
    sent = sum(1 for s in status.values() if s == "sent")
    alerts[event] = f"{sent}/{len(status)} channels" if status else "no channels"
