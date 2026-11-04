"""`/api/signals` routes: the weekly signals, briefs, desk debates and the scorecard (Stage 7.2,
D52). Every route needs a login; all members see the same signals.

MCO-derived content (Decision 6): while MCO is on, members see MCO's signal rows on screen
like any other source. When MCO is switched off, the `mco` rows and their scores are left out,
and a week that had an MCO row also keeps its brief and desk debates back, since both were
written with MCO's views as input.

Briefs, rationales and debates are untrusted model output: the UI renders them as text.
"""

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from desk.agents.brief_writer import BriefOut as BriefPayload
from desk.agents.brief_writer import CoinBriefOut
from desk.agents.schemas import DeskRunState
from desk.api.deps import SessionDep, require_role
from desk.api.schemas import Envelope, Source
from desk.models import Brief, Signal, SignalOutcome
from desk.signals import score
from desk.signals.chain import version_number

router = APIRouter(prefix="/signals", tags=["signals"],
                   dependencies=[Depends(require_role("member"))])  # fmt: skip

SignalSource = Literal["desk", "coinflip", "trend", "mco"]
WITHHELD = "Kept back while MCO is switched off: it was written with MCO's views as input."


def mco_on() -> bool:
    from desk.jobs.mco_daily import enabled

    return enabled()


def current_version() -> int:
    from desk.signals.run import signal_settings

    return version_number(signal_settings().get("version", "v1"))


def _source(version: int, week: dt.date | None = None) -> list[Source]:
    detail = f"signals v{version}" + (f", week of {week.isoformat()}" if week else "")
    return [Source(name="desk.signals", detail=detail)]


# --- Models ----------------------------------------------------------------------------------


class OutcomeOut(BaseModel):
    reference_close: float | None
    week_close: float
    direction_hit: bool | None
    first_hit: Literal["target", "invalidation", "neither"] | None
    paper_pnl: float | None
    brier: float | None
    resolved_at: dt.datetime


class SignalOut(BaseModel):
    id: int
    version: int
    week: dt.date
    coin: str
    source: SignalSource
    stance: Literal["lean_long", "flat"]
    confidence: float
    entry_low: float | None
    entry_high: float | None
    invalidation: float | None
    target: float | None
    rationale: str | None
    has_debate: bool  # a desk signal whose run can be opened (`/signals/{id}/debate`)
    hash: str
    created_at: dt.datetime
    outcome: OutcomeOut | None


class BriefLevel(BaseModel):
    label: str
    price: float


class BriefCoin(BaseModel):
    coin: str
    setup: str
    bull_case: str
    bear_case: str
    what_would_change: str
    levels_to_watch: list[BriefLevel]


class BriefView(BaseModel):
    id: int
    week: dt.date
    model: str
    prompt_version: str
    created_at: dt.datetime
    content: str  # Markdown (untrusted)
    summary: list[str]  # empty when the structured payload is missing
    coins: list[BriefCoin]


class WeekView(BaseModel):
    week: dt.date  # Monday of the signal week; the data ends the day before
    version: int
    resolves_on: dt.date  # the first day the week's outcomes can be resolved
    brief: BriefView | None
    withheld: str | None  # why the brief and debates are kept back, if they are
    signals: list[SignalOut]


class WeekSummary(BaseModel):
    week: dt.date
    signals: int
    resolved: int
    has_brief: bool


class WeeksView(BaseModel):
    version: int
    versions: list[int]
    weeks: list[WeekSummary]  # newest first


class StatsOut(BaseModel):
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
    paper_return: float
    early_days: bool


class PointOut(BaseModel):
    week: dt.date
    signals: int
    hit_rate: float
    brier: float
    paper_return: float


class CoinScore(BaseModel):
    coin: str
    stats: StatsOut


class SourceScore(BaseModel):
    source: SignalSource
    stats: StatsOut
    coins: list[CoinScore]
    cumulative: list[PointOut]


class ScorecardView(BaseModel):
    version: int
    early_weeks: int  # fewer weeks than this is "early days"
    paper_cost_per_side: float
    weeks: list[dt.date]
    sources: list[SourceScore]


# --- Helpers ---------------------------------------------------------------------------------


def _visible(q: Any) -> Any:
    return q if mco_on() else q.where(Signal.source != "mco")


def _signal_out(sig: Signal, out: SignalOutcome | None, debates: bool) -> SignalOut:
    from desk.signals.run import snapshot_id_of

    return SignalOut(
        id=sig.id, version=sig.version, week=sig.week, coin=sig.coin, source=sig.source,
        stance=sig.stance, confidence=sig.confidence, entry_low=sig.entry_low,
        entry_high=sig.entry_high, invalidation=sig.invalidation, target=sig.target,
        rationale=sig.rationale,
        has_debate=debates and sig.source == "desk" and snapshot_id_of(sig.transcript_ref)
        is not None,
        hash=sig.hash, created_at=sig.created_at,
        outcome=OutcomeOut.model_validate(out, from_attributes=True) if out else None,
    )  # fmt: skip


def _withheld(session: Session, version: int, week: dt.date) -> str | None:
    """Why this week's brief and debates are kept back (MCO off, MCO rows that week)."""
    if mco_on():
        return None
    q = select(Signal.id).where(
        Signal.version == version, Signal.week == week, Signal.source == "mco"
    )
    return WITHHELD if session.scalar(q.limit(1)) is not None else None


def _brief(session: Session, week: dt.date) -> BriefView | None:
    row = session.scalars(
        select(Brief).where(Brief.week == week).order_by(Brief.id.desc()).limit(1)
    ).first()
    if row is None:
        return None
    coins: list[CoinBriefOut] = []
    summary: list[str] = []
    try:
        if row.payload:
            payload = BriefPayload.model_validate(row.payload)
            summary, coins = payload.summary, payload.coins
    except ValidationError:
        pass
    return BriefView(
        id=row.id, week=row.week, model=row.model, prompt_version=row.prompt_version,
        created_at=row.created_at, content=row.content, summary=summary,
        coins=[BriefCoin.model_validate(c.model_dump()) for c in coins],
    )  # fmt: skip


def _order(sig: Signal) -> tuple[str, int]:
    sources = list(SignalSource.__args__)  # type: ignore[attr-defined]
    return sig.coin, sources.index(sig.source) if sig.source in sources else 99


# --- Routes ----------------------------------------------------------------------------------


@router.get("/weeks", response_model=Envelope[WeeksView], operation_id="listSignalWeeks")
def list_weeks(
    session: SessionDep, version: Annotated[int | None, Query(ge=1)] = None
) -> Envelope[WeeksView]:
    """Every signal week of `version` (default: the current one), newest first."""
    v = version or current_version()
    versions = sorted(set(session.scalars(select(Signal.version).distinct())) | {v})
    q = _visible(
        select(Signal.week, func.count(Signal.id), func.count(SignalOutcome.signal_id))
        .outerjoin(SignalOutcome, SignalOutcome.signal_id == Signal.id)
        .where(Signal.version == v)
        .group_by(Signal.week)
        .order_by(Signal.week.desc())
    )
    briefs = set(session.scalars(select(Brief.week).distinct()))
    weeks = [
        WeekSummary(week=w, signals=n, resolved=r, has_brief=w in briefs)
        for w, n, r in session.execute(q)
    ]
    as_of = weeks[0].week - dt.timedelta(days=1) if weeks else None
    return Envelope(as_of=as_of, sources=_source(v),
                    data=WeeksView(version=v, versions=versions, weeks=weeks))  # fmt: skip


@router.get("/week", response_model=Envelope[WeekView], operation_id="getSignalWeek")
def get_week(
    session: SessionDep,
    week: dt.date | None = None,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> Envelope[WeekView]:
    """One week's signals (every source and coin) with outcomes and the brief. Default: the
    latest week. 404 when there are no signals yet."""
    v = version or current_version()
    if week is None:
        week = session.scalar(_visible(select(func.max(Signal.week)).where(Signal.version == v)))
        if week is None:
            raise HTTPException(404, "no signals yet")
    rows = session.execute(
        _visible(
            select(Signal, SignalOutcome)
            .outerjoin(SignalOutcome, SignalOutcome.signal_id == Signal.id)
            .where(Signal.version == v, Signal.week == week)
        )
    ).all()
    if not rows:
        raise HTTPException(404, f"no signals for the week of {week.isoformat()}")
    withheld = _withheld(session, v, week)
    signals = [
        _signal_out(s, o, withheld is None) for s, o in sorted(rows, key=lambda r: _order(r[0]))
    ]
    data = WeekView(
        week=week, version=v, resolves_on=week + dt.timedelta(days=8),
        brief=None if withheld else _brief(session, week), withheld=withheld, signals=signals,
    )  # fmt: skip
    return Envelope(as_of=week - dt.timedelta(days=1), sources=_source(v, week), data=data)


@router.get("/history", response_model=Envelope[list[SignalOut]], operation_id="listSignals")
def history(
    session: SessionDep,
    coin: str | None = None,
    source: SignalSource | None = None,
    version: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> Envelope[list[SignalOut]]:
    """Signals with their outcomes, newest week first."""
    v = version or current_version()
    q = (
        select(Signal, SignalOutcome)
        .outerjoin(SignalOutcome, SignalOutcome.signal_id == Signal.id)
        .where(Signal.version == v)
        .order_by(Signal.week.desc(), Signal.coin, Signal.id)
        .limit(limit)
    )
    if coin:
        q = q.where(Signal.coin == coin.upper())
    if source:
        q = q.where(Signal.source == source)
    rows = session.execute(_visible(q)).all()
    mco_weeks: set[dt.date] = set()
    if not mco_on():
        mco_weeks = set(session.scalars(
            select(Signal.week).where(Signal.version == v, Signal.source == "mco").distinct()
        ))  # fmt: skip
    data = [_signal_out(s, o, s.week not in mco_weeks) for s, o in rows]
    as_of = data[0].week - dt.timedelta(days=1) if data else None
    return Envelope(as_of=as_of, sources=_source(v), data=data)


@router.get("/scorecard", response_model=Envelope[ScorecardView], operation_id="getScorecard")
def get_scorecard(
    session: SessionDep, version: Annotated[int | None, Query(ge=1)] = None
) -> Envelope[ScorecardView]:
    """Hit rate, Brier score, target-before-invalidation and paper P&L per source and coin, with
    cumulative values per week (`signals/score.py`)."""
    from desk.signals.run import signal_settings

    v = version or current_version()
    card = score.scorecard(score.load(session, v, include_mco=mco_on()), v)
    sources = [
        SourceScore(
            source=src,
            stats=StatsOut.model_validate(st, from_attributes=True),
            coins=[
                CoinScore(coin=c, stats=StatsOut.model_validate(cs, from_attributes=True))
                for (s, c), cs in card.by_coin.items()
                if s == src
            ],
            cumulative=[
                PointOut.model_validate(p, from_attributes=True) for p in card.cumulative[src]
            ],  # fmt: skip
        )
        for src, st in card.by_source.items()
    ]
    data = ScorecardView(
        version=v, early_weeks=score.EARLY_WEEKS,
        paper_cost_per_side=float(signal_settings().get("paper_cost_per_side", 0.002)),
        weeks=card.weeks, sources=sources,
    )  # fmt: skip
    as_of = card.weeks[-1] + dt.timedelta(days=6) if card.weeks else None
    return Envelope(as_of=as_of, sources=_source(v), data=data)


@router.get("/{signal_id}/debate", response_model=Envelope[DeskRunState],
            operation_id="getSignalDebate")  # fmt: skip
def get_debate(signal_id: int, session: SessionDep) -> Envelope[DeskRunState]:
    """The desk run behind one desk signal: reports, debate, the head's signal, validation."""
    from desk.signals.run import desk_state, snapshot_id_of

    sig = session.get(Signal, signal_id)
    if sig is None or sig.source != "desk":
        raise HTTPException(404, "no debate for this signal")
    if _withheld(session, sig.version, sig.week):
        raise HTTPException(404, WITHHELD)
    state = desk_state(session, snapshot_id_of(sig.transcript_ref))
    if state is None:
        raise HTTPException(404, "no debate for this signal")
    try:
        run = DeskRunState.model_validate(state)
    except ValidationError:
        raise HTTPException(404, "the saved run can't be read") from None
    return Envelope(as_of=sig.week - dt.timedelta(days=1), sources=_source(sig.version, sig.week),
                    data=run)  # fmt: skip
