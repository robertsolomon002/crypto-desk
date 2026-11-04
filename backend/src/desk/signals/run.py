"""The weekly signals run (Section 3.5, Stage 7.1, D51).

For the signal week W (the Monday of `now`'s UTC week; every input is as of W - 1 day):
1. refresh data (every source, as the daily job does);
2. resolve finished weeks into `signal_outcomes` (`signals.resolve`);
3. run the desk per coin on the server key: the core coins plus up to
   `signals.max_watchlist_coins_in_desk` watchlist coins; the watchlist is skipped once spend
   reaches the Decision 9 degrade point;
4. the coin-flip and trend-rule baselines (`signals.baselines`);
5. MCO's latest bias per coin as a source;
6. append the rows, hash-chained (`signals.chain`), as signal version `signals.version`.
The brief and alerts are `jobs.weekly`'s part.

A coin without a candle for W - 1 gets no signals (stale). A desk run that errors or whose
signal fails validation twice writes no desk row for that coin; the other sources still do.
Re-running the same week fills gaps only (existing rows and their desk runs are kept).
`dry_run` does everything except writing signals and outcomes; desk runs still cost money and
are saved as Ask the desk conversations.
"""

import datetime as dt
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from desk.agents import cost, desk_graph
from desk.agents.chat import ChatError
from desk.agents.desk_graph import DeskPrepared
from desk.config import load_app_settings
from desk.data.update import SourceResult
from desk.models import AgentSnapshot, CandleDaily, Coin, Signal, User
from desk.signals import baselines, chain, resolve
from desk.signals.chain import Proposed

Sessions = sessionmaker[Session]
Echo = Callable[[str, bool], None]
DeskRunner = Callable[[DeskPrepared], AsyncIterator[tuple[str, Any]]]


def signal_settings() -> dict[str, Any]:
    return load_app_settings().get("signals") or {}


def signal_week(now: dt.datetime) -> dt.date:
    """The Monday (UTC) of `now`'s week. The Monday 00:15 run signals the week just begun."""
    day = now.astimezone(dt.UTC).date()
    return day - dt.timedelta(days=day.weekday())


@dataclass
class CoinRun:
    coin: str
    reference_close: float | None = None
    signals: list[Proposed] = field(default_factory=list)
    desk_status: str = "pending"  # valid|invalid|error|refused|existing|skipped
    desk_note: str | None = None
    snapshot_id: int | None = None
    desk_seconds: float = 0.0


@dataclass
class SignalsRun:
    week: dt.date
    as_of: dt.date
    version: int
    dry_run: bool
    degraded: bool = False
    coins: list[str] = field(default_factory=list)
    skipped_watchlist: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    sources: dict[str, SourceResult] = field(default_factory=dict)
    resolved: list[tuple[int, str, str, str, bool]] = field(default_factory=list)
    runs: dict[str, CoinRun] = field(default_factory=dict)
    written: list[int] = field(default_factory=list)  # signal ids
    notes: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[str]:
        out = [f"{r.name} FAILED: {r.error}" for r in self.sources.values() if not r.ok]
        out += [f"stale: {s}" for s in self.stale]
        for r in self.runs.values():
            if r.desk_status in ("invalid", "error", "refused"):
                out.append(f"desk {r.coin}: {r.desk_status} ({r.desk_note or 'no detail'})")
        return out

    def all_signals(self) -> list[Proposed]:
        return [s for r in self.runs.values() for s in r.signals]


# --- Coins and sources -----------------------------------------------------------------------


def signal_coins(
    session: Session, degraded: bool, max_watchlist: int
) -> tuple[list[str], list[str]]:
    """(coins to signal, watchlist coins skipped). Core coins first, then the watchlist in the
    order Rob added it."""
    rows = session.scalars(select(Coin).where(Coin.active).order_by(Coin.added_at, Coin.symbol))
    core, watch = [], []
    for c in rows:
        (watch if c.is_watchlist else core).append(c.symbol)
    if degraded:
        return core, watch
    return core + watch[:max_watchlist], watch[max_watchlist:]


def last_close(session: Session, coin: str, day: dt.date) -> float | None:
    return session.scalar(
        select(CandleDaily.close).where(CandleDaily.coin == coin, CandleDaily.date == day)
    )


def mco_signal(
    session: Session, coin: str, as_of: dt.date, reference_close: float, cfg: dict[str, Any]
) -> Proposed | None:
    """MCO's latest view (published by the end of `as_of`, at most `mco_max_age_days` old) as a
    signal: lean_long if bullish, else flat. Confidence from the extraction's confidence label
    (`mco_confidence`), `mco_default_confidence` without one (D51). His primary invalidation
    and nearest target become levels only when they bracket the reference close."""
    from desk.api.routes.views import mco_views

    views = mco_views(session, coin, as_of, limit=1)
    if not views:
        return None
    v = views[0]
    age = (as_of - v.published_at.astimezone(dt.UTC).date()).days
    if age > int(cfg.get("mco_max_age_days", 14)):
        return None
    table = cfg.get("mco_confidence") or {}
    default = float(cfg.get("mco_default_confidence", 0.6))
    confidence = float(table.get(v.confidence, default)) if v.confidence else default
    lean = v.bias == "bullish"
    invalidation = target = None
    if lean:
        above = sorted(t for t in v.targets if t > reference_close)
        if v.invalidation is not None and v.invalidation < reference_close and above:
            invalidation, target = float(v.invalidation), float(above[0])
    published = v.published_at.astimezone(dt.UTC).date().isoformat()
    return Proposed(
        coin=coin,
        source="mco",
        stance="lean_long" if lean else "flat",
        confidence=confidence,
        invalidation=invalidation,
        target=target,
        rationale=f"MCO's latest video ({published}): {v.bias} bias, extraction "
        f"confidence {v.confidence or 'unknown'} (AI-extracted).",
        transcript_ref=v.id,
    )


def desk_proposed(coin: str, signal: Any, snapshot_id: int | None) -> Proposed:
    return Proposed(
        coin=coin,
        source="desk",
        stance=signal.stance,
        confidence=float(signal.confidence),
        entry_low=signal.entry_low,
        entry_high=signal.entry_high,
        invalidation=signal.invalidation,
        target=signal.target,
        rationale=signal.rationale,
        transcript_ref=f"snapshot:{snapshot_id}" if snapshot_id else None,
    )


def snapshot_id_of(ref: str | None) -> int | None:
    if ref and ref.startswith("snapshot:"):
        return int(ref.removeprefix("snapshot:"))
    return None


def desk_state(session: Session, snapshot_id: int | None) -> dict[str, Any] | None:
    if snapshot_id is None:
        return None
    row = session.get(AgentSnapshot, snapshot_id)
    return row.result if row and row.tool == desk_graph.SNAPSHOT_TOOL else None


# --- The desk --------------------------------------------------------------------------------


def admin_user_id(session: Session) -> int | None:
    q = select(User.id).where(User.role == "admin").order_by(User.id).limit(1)
    return session.scalar(q)


async def run_desk(
    sessions: Sessions, user_id: int, r: CoinRun, as_of: dt.date, runner: DeskRunner | None
) -> None:
    """One desk run on the server key; fills `r` (status, note, snapshot, desk signal)."""
    clock = time.monotonic()
    try:
        with sessions() as s:
            prepared = desk_graph.prepare(
                s,
                sessions,
                user_id=user_id,
                is_admin=True,
                coin=r.coin,
                as_of=as_of,
                provider=None,
                model=None,
                key=None,
                rate_limited=False,
            )
    except ChatError as e:
        r.desk_status, r.desk_note = "refused", e.message
        return
    signal = validation = None
    async for name, payload in (runner or desk_graph.run)(prepared):
        if name == "signal":
            signal, validation = payload.signal, payload.validation
        elif name == "done":
            r.snapshot_id = payload.snapshot_id
            r.desk_status = payload.status
        elif name == "error":
            r.snapshot_id = payload.snapshot_id
            r.desk_status, r.desk_note = "error", payload.message
    r.desk_seconds = time.monotonic() - clock
    if r.desk_status == "valid" and signal is not None and validation is not None and validation.ok:
        r.signals.insert(0, desk_proposed(r.coin, signal, r.snapshot_id))
    elif r.desk_status == "invalid" and validation is not None:
        r.desk_note = " ".join(validation.errors)[:300]


# --- The run ---------------------------------------------------------------------------------


async def run_signals(
    sessions: Sessions,
    now: dt.datetime | None = None,
    *,
    dry_run: bool = False,
    refresh: bool = True,
    update: Callable[..., dict[str, SourceResult]] | None = None,
    desk_runner: DeskRunner | None = None,
    echo: Echo = lambda line, err: None,
) -> SignalsRun:
    from desk.data import market
    from desk.data.update import update_all

    now = now or dt.datetime.now(dt.UTC)
    cfg = signal_settings()
    week = signal_week(now)
    as_of = week - dt.timedelta(days=1)
    run = SignalsRun(
        week=week,
        as_of=as_of,
        version=chain.version_number(cfg.get("version", "v1")),
        dry_run=dry_run,
    )

    # 1. Refresh data.
    if refresh:
        run.sources = (update or update_all)(sessions, now, echo=echo)

    # 2. Resolve finished weeks.
    with sessions() as s:
        pc = float(cfg.get("paper_cost_per_side", 0.002))
        for sig, out in resolve.resolve(s, now.date(), pc, write=not dry_run):
            run.resolved.append(
                (sig.id, sig.week.isoformat(), sig.coin, sig.source, out.direction_hit)
            )
        if not dry_run:
            s.commit()
    echo(f"resolved {len(run.resolved)} signal(s)", False)

    # Coins, freshness, what already exists this week.
    with sessions() as s:
        run.degraded = cost.budget(s).degraded
        run.coins, run.skipped_watchlist = signal_coins(
            s, run.degraded, int(cfg.get("max_watchlist_coins_in_desk", 3))
        )
        if run.skipped_watchlist:
            why = "spend is near the cap" if run.degraded else "over the desk's watchlist limit"
            run.notes.append(f"watchlist skipped ({why}): {', '.join(run.skipped_watchlist)}")
        existing = {
            (row.coin, row.source): row
            for row in s.scalars(
                select(Signal).where(Signal.version == run.version, Signal.week == week)
            )
        }
        user_id = admin_user_id(s)
        for coin in run.coins:
            close = last_close(s, coin, as_of)
            if close is None:
                run.stale.append(f"{coin} has no candle for {as_of}")
                continue
            run.runs[coin] = CoinRun(coin=coin, reference_close=float(close))

    # 3. The desk, one coin at a time.
    for coin, r in run.runs.items():
        prior = existing.get((coin, "desk"))
        if prior is not None:
            r.desk_status, r.snapshot_id = "existing", snapshot_id_of(prior.transcript_ref)
            continue
        if user_id is None:
            r.desk_status, r.desk_note = "refused", "no admin user in the database"
            continue
        echo(f"desk {coin} as of {as_of} ...", False)
        await run_desk(sessions, user_id, r, as_of, desk_runner)
        echo(
            f"desk {coin}: {r.desk_status} in {r.desk_seconds:.0f} s"
            + (f" ({r.desk_note})" if r.desk_note else ""),
            False,
        )

    # 4 and 5. Baselines and MCO.
    with sessions() as s:
        for coin, r in run.runs.items():
            r.signals.append(baselines.coinflip(coin))
            daily = market.load_daily(s, coin, as_of)
            t = baselines.trend(coin, daily, as_of, cfg.get("trend"))
            if t is None:
                run.notes.append(f"trend {coin}: fewer weeks than the SMA needs")
            else:
                r.signals.append(t)
            assert r.reference_close is not None
            m = mco_signal(s, coin, as_of, r.reference_close, cfg)
            if m is not None:
                r.signals.append(m)

    # 6. Append, chained.
    if not dry_run:
        with sessions.begin() as s:
            rows = chain.append(s, run.version, week, run.all_signals())
            run.written = [row.id for row in rows]
    return run
