"""Weekly signals (Stage 7.1, D51): baselines, the hash chain and append-only enforcement,
resolving finished weeks, MCO as a source, the weekly job end to end (desk runner and brief
model faked), and the brief writer."""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
import sqlalchemy as sa
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from sqlalchemy import func, select, text

from desk.agents import brief_writer, chat, llm
from desk.agents.schemas import DeskSignal, SignalEvent, Validation
from desk.data import market
from desk.jobs import weekly
from desk.models import AgentSnapshot, Brief, Coin, JobRun, Signal, SignalOutcome
from desk.signals import baselines, chain, resolve
from desk.signals import run as signals_run
from desk.signals.chain import Proposed
from tests.agent_fakes import ScriptedModel, answer

# --- Baselines -------------------------------------------------------------------------------


def frame(closes: list[float], start: dt.date) -> pd.DataFrame:
    idx = pd.DatetimeIndex(
        [pd.Timestamp(start + dt.timedelta(days=i), tz="UTC") for i in range(len(closes))]
    )
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1.0}, index=idx
    )


MONDAY = dt.date(2026, 1, 5)


def test_coinflip_is_always_flat_at_one_half() -> None:
    p = baselines.coinflip("BTC")
    assert (p.stance, p.confidence, p.source, p.p_up()) == ("flat", 0.5, "coinflip", 0.5)
    assert p.invalidation is None and p.target is None


def test_trend_rule_long_above_the_20_week_sma_and_flat_below() -> None:
    rising = frame([100 + i for i in range(7 * 30)], MONDAY)
    as_of = MONDAY + dt.timedelta(days=7 * 30 - 1)  # a Sunday: the last week is complete
    up = baselines.trend("BTC", rising, as_of)
    assert up is not None and up.stance == "lean_long" and up.confidence == 0.6
    assert up.p_up() == 0.6
    down = baselines.trend("BTC", frame([400 - i for i in range(7 * 30)], MONDAY), as_of)
    assert down is not None and down.stance == "flat" and down.confidence == 0.6
    assert down.p_up() == pytest.approx(0.4)  # the roadmap's "flat with 0.4"


def test_trend_rule_needs_20_complete_weeks_and_ignores_later_data() -> None:
    as_of = MONDAY + dt.timedelta(days=7 * 19 - 1)
    assert baselines.trend("BTC", frame([100.0] * (7 * 19), MONDAY), as_of) is None
    # Falling for 30 weeks, then a spike after as_of: the spike must not count.
    closes = [400 - i for i in range(7 * 30)] + [10_000.0] * 14
    as_of = MONDAY + dt.timedelta(days=7 * 30 - 1)
    p = baselines.trend("BTC", frame(closes, MONDAY), as_of)
    assert p is not None and p.stance == "flat"


# --- The chain and append-only ---------------------------------------------------------------


def seed_coin(s, symbol: str = "BTC", watchlist: bool = False) -> None:
    s.add(Coin(symbol=symbol, name=symbol, source_market=f"{symbol}/USD", is_watchlist=watchlist))
    s.flush()


def proposals(*coins: str) -> list[Proposed]:
    out = []
    for c in coins:
        out += [
            baselines.coinflip(c),
            Proposed(coin=c, source="trend", stance="lean_long", confidence=0.6),
        ]
    return out


def test_rows_are_hash_chained_and_reruns_fill_gaps_only(pg_sessions) -> None:
    week = dt.date(2026, 10, 26)
    with pg_sessions.begin() as s:
        seed_coin(s, "BTC")
        seed_coin(s, "ETH")
        first = chain.append(s, 1, week, proposals("BTC"))
    with pg_sessions.begin() as s:
        again = chain.append(s, 1, week, proposals("BTC", "ETH"))
    assert [r.coin for r in again] == ["ETH", "ETH"]  # BTC rows already existed
    with pg_sessions() as s:
        rows = s.scalars(select(Signal).order_by(Signal.id)).all()
        assert rows[0].prev_hash is None
        for prev, row in zip(rows, rows[1:], strict=False):
            assert row.prev_hash == prev.hash
        assert len({r.hash for r in rows}) == 4
        assert chain.verify(s) == []
    assert first[0].hash == chain.row_hash(chain.content(first[0]), None)


def test_updates_and_deletes_are_refused_by_the_database(pg_sessions) -> None:
    with pg_sessions.begin() as s:
        seed_coin(s)
        chain.append(s, 1, dt.date(2026, 10, 26), proposals("BTC"))
    for sql in ("UPDATE signals SET confidence = 0.9", "DELETE FROM signals"):
        with pytest.raises(sa.exc.DBAPIError, match="append-only"), pg_sessions.begin() as s:
            s.execute(text(sql))
    with pg_sessions() as s:
        assert s.scalar(select(func.count()).select_from(Signal)) == 2


def test_verify_finds_a_tampered_row(pg_sessions) -> None:
    with pg_sessions.begin() as s:
        seed_coin(s)
        chain.append(s, 1, dt.date(2026, 10, 26), proposals("BTC"))
    with pg_sessions.begin() as s:  # a superuser getting around the trigger
        s.execute(text("ALTER TABLE signals DISABLE TRIGGER signals_append_only"))
        s.execute(text("UPDATE signals SET confidence = 0.9 WHERE id = 1"))
        s.execute(text("ALTER TABLE signals ENABLE TRIGGER signals_append_only"))
    with pg_sessions() as s:
        assert chain.verify(s) == ["signal 1: hash doesn't match its content"]


def test_version_label() -> None:
    assert chain.version_number("v1") == 1 and chain.version_number(2) == 2


# --- Resolving -------------------------------------------------------------------------------


def week_days(rows: list[tuple[float, float, float]]) -> pd.DataFrame:
    """(low, high, close) per day."""
    return pd.DataFrame(rows, columns=["low", "high", "close"])


def sig(**kw: Any) -> SimpleNamespace:
    base = {"stance": "lean_long", "confidence": 0.6, "invalidation": 90.0, "target": 110.0}
    return SimpleNamespace(**{**base, **kw})


def test_first_hit_counts_a_day_touching_both_as_invalidation() -> None:
    assert resolve.first_hit(week_days([(95, 105, 100), (89, 111, 100)]), 90, 110) == (
        "invalidation"
    )
    assert resolve.first_hit(week_days([(95, 111, 100), (85, 100, 90)]), 90, 110) == "target"
    assert resolve.first_hit(week_days([(95, 105, 100)]), 90, 110) == "neither"
    assert resolve.first_hit(week_days([(80, 120, 100)]), None, 110) is None


def test_outcome_direction_brier_and_paper_pnl() -> None:
    days = week_days([(98, 104, 102)] * 6 + [(100, 106, 105)])
    o = resolve.outcome(sig(), 100.0, days, cost=0.002)
    assert o.direction_hit and o.first_hit == "neither" and o.week_close == 105
    assert o.brier == pytest.approx(0.16)  # (0.6 - 1)^2
    assert o.paper_pnl == pytest.approx(105 * 0.998 / (100 * 1.002) - 1)
    hit = resolve.outcome(sig(), 100.0, week_days([(95, 111, 108)] * 7), cost=0.0)
    assert hit.first_hit == "target" and hit.paper_pnl == pytest.approx(0.10)
    stop = resolve.outcome(sig(), 100.0, week_days([(89, 111, 120)] * 7), cost=0.0)
    assert stop.first_hit == "invalidation" and stop.paper_pnl == pytest.approx(-0.10)
    flat = resolve.outcome(sig(stance="flat", invalidation=None, target=None), 100.0, days, 0.002)
    assert not flat.direction_hit and flat.paper_pnl == 0.0 and flat.first_hit is None
    assert flat.brier == pytest.approx(0.36)  # P(up) 0.4, it went up


def candles(s, coin: str, start: dt.date, closes: list[float]) -> None:
    market.upsert_candles(
        s,
        [
            {
                "coin": coin,
                "date": start + dt.timedelta(days=i),
                "open": c,
                "high": c * 1.01,
                "low": c * 0.99,
                "close": c,
                "volume": 1.0,
                "source": "test",
            }
            for i, c in enumerate(closes)
        ],
    )


def test_resolve_writes_one_outcome_once_the_week_has_closed(pg_sessions) -> None:
    week = dt.date(2026, 10, 19)
    with pg_sessions.begin() as s:
        seed_coin(s)
        candles(s, "BTC", week - dt.timedelta(days=1), [100.0] + [101.0] * 6)  # up to Sat
        chain.append(s, 1, week, proposals("BTC"))
    with pg_sessions.begin() as s:  # Sunday's candle is missing: nothing resolves
        assert resolve.resolve(s, dt.date(2026, 10, 26), 0.002) == []
        candles(s, "BTC", dt.date(2026, 10, 25), [104.0])
    with pg_sessions.begin() as s:
        done = resolve.resolve(s, dt.date(2026, 10, 26), 0.002)
        assert [(x.source, o.week_close, o.reference_close) for x, o in done] == [
            ("coinflip", 104.0, 100.0),
            ("trend", 104.0, 100.0),
        ]
    with pg_sessions.begin() as s:
        assert resolve.resolve(s, dt.date(2026, 10, 27), 0.002) == []  # never twice
        assert s.scalar(select(func.count()).select_from(SignalOutcome)) == 2


# --- MCO as a source -------------------------------------------------------------------------


def view(bias: str, confidence: str | None, day: dt.date, **kw: Any) -> SimpleNamespace:
    return SimpleNamespace(
        id="mco:vid",
        bias=bias,
        confidence=confidence,
        published_at=dt.datetime.combine(day, dt.time(12), dt.UTC),
        invalidation=kw.get("invalidation"),
        targets=kw.get("targets", []),
    )


def test_mco_bias_becomes_a_signal(monkeypatch) -> None:
    from desk.api.routes import views

    cfg = signals_run.signal_settings()
    as_of = dt.date(2026, 11, 1)
    found: list[Any] = []
    monkeypatch.setattr(views, "mco_views", lambda s, coin, as_of, limit: found)
    assert signals_run.mco_signal(None, "BTC", as_of, 100.0, cfg) is None
    found[:] = [view("bullish", "high", as_of, invalidation=90.0, targets=[95.0, 120.0, 130.0])]
    p = signals_run.mco_signal(None, "BTC", as_of, 100.0, cfg)
    assert (p.stance, p.confidence, p.invalidation, p.target) == ("lean_long", 0.7, 90.0, 120.0)
    assert p.transcript_ref == "mco:vid"
    found[:] = [view("bullish", None, as_of, invalidation=105.0, targets=[120.0])]
    p = signals_run.mco_signal(None, "BTC", as_of, 100.0, cfg)
    assert (p.confidence, p.invalidation, p.target) == (0.6, None, None)  # levels don't bracket
    found[:] = [view("bearish", "low", as_of)]
    assert signals_run.mco_signal(None, "BTC", as_of, 100.0, cfg).stance == "flat"
    found[:] = [view("bullish", "high", as_of - dt.timedelta(days=15))]
    assert signals_run.mco_signal(None, "BTC", as_of, 100.0, cfg) is None  # too old


# --- The weekly job --------------------------------------------------------------------------


class FakeBriefModel:
    """Stands in for ChatAnthropic: `with_structured_output(json_schema)` returns `brief`."""

    def __init__(self, brief: brief_writer.BriefOut | None = None) -> None:
        self.brief = brief
        self.sent: list[Any] = []
        self.method: str | None = None

    def with_structured_output(self, schema, method, include_raw):
        self.method = method

        def run(messages):
            self.sent.append(messages)
            raw = AIMessage(
                "",
                usage_metadata={
                    "input_tokens": 20_000,
                    "output_tokens": 2_000,
                    "total_tokens": 22_000,
                },
            )
            return {"raw": raw, "parsed": self.brief, "parsing_error": None}

        return RunnableLambda(run)


def brief_for(coins: list[str]) -> brief_writer.BriefOut:
    return brief_writer.BriefOut(
        summary=[f"Line {i}." for i in range(1, 6)],
        coins=[
            brief_writer.CoinBriefOut(
                coin=c,
                setup="Range.",
                bull_case="Support holds.",
                bear_case="Momentum fades.",
                what_would_change="A break.",
                levels_to_watch=[brief_writer.LevelOut(label="20W SMA", price=100.0)],
            )
            for c in coins
        ],
    )


@pytest.fixture
def job(api_sessions, monkeypatch):
    """The weekly job on the seeded API database with a fake desk runner and brief model."""
    monkeypatch.setattr(llm, "make_chat_model", lambda choice, key: ScriptedModel(script=[answer]))
    sent: list[Any] = []
    monkeypatch.setattr(weekly, "send", lambda alert: sent.append(alert) or {"telegram": "sent"})
    fake = FakeBriefModel()
    monkeypatch.setattr(brief_writer, "make_model", lambda name: fake)
    calls: list[str] = []
    stance: dict[str, str] = {}

    async def runner(p):
        calls.append(p.coin)
        close = p.reference_close
        mode = stance.get(p.coin, "long")
        if mode == "error":
            yield "error", SimpleNamespace(snapshot_id=None, message="The head ran out of time.")
            return
        signal = DeskSignal(
            coin=p.coin,
            stance="lean_long",
            confidence=0.6,
            entry_low=close * 0.98,
            entry_high=close,
            invalidation=close * 0.93,
            target=close * 1.06,
            rationale="Support holds.",
            cites=["T1"],
        )
        ok = mode != "invalid"
        val = Validation(ok=ok, errors=[] if ok else ["target too far."], attempts=2 - ok)
        yield "signal", SignalEvent(signal=signal, validation=val)
        state = {
            "status": "valid" if ok else "invalid",
            "reports": {},
            "debate": {},
            "signal": signal.model_dump(),
            "validation": val.model_dump(),
        }
        sid = chat.save_snapshot(
            p.sessions, p.user_id, p.conversation_id, "desk_run", {"coin": p.coin}, state
        )
        yield "done", SimpleNamespace(snapshot_id=sid, status="valid" if ok else "invalid")

    def go(now: dt.datetime, **kw: Any):
        import asyncio

        fake.brief = brief_for(kw.pop("coins", ["BTC", "ETH", "SOL"]))
        return asyncio.run(
            weekly.run_weekly(api_sessions, now, refresh=False, desk_runner=runner, **kw)
        )

    return SimpleNamespace(go=go, sent=sent, calls=calls, stance=stance, model=fake)


MON_19 = dt.datetime(2026, 10, 19, 0, 15, tzinfo=dt.UTC)
MON_26 = dt.datetime(2026, 10, 26, 0, 15, tzinfo=dt.UTC)


def test_weekly_job_writes_chained_signals_a_brief_and_an_alert(api_sessions, job) -> None:
    result = job.go(MON_26)
    assert result.status == "success", result.problems
    assert job.calls == ["BTC", "ETH", "SOL"]
    with api_sessions() as s:
        rows = s.scalars(select(Signal).order_by(Signal.id)).all()
        assert {(r.coin, r.source) for r in rows} == {
            (c, src) for c in ("BTC", "ETH", "SOL") for src in ("desk", "coinflip", "trend")
        }
        assert {r.week for r in rows} == {dt.date(2026, 10, 26)} and {r.version for r in rows} == {
            1
        }
        desk = next(r for r in rows if r.source == "desk" and r.coin == "BTC")
        snap = s.get(AgentSnapshot, int(desk.transcript_ref.split(":")[1]))
        assert snap.tool == "desk_run" and snap.args == {"coin": "BTC"}
        assert chain.verify(s) == []
        brief = s.scalars(select(Brief)).one()
        assert brief.week == dt.date(2026, 10, 26) and brief.prompt_version == "brief_v1"
        assert "## BTC" in brief.content and brief.payload["summary"][0] == "Line 1."
        run = s.scalars(select(JobRun).where(JobRun.job == "weekly")).one()
        assert run.status == "success" and run.cost > 0  # the brief's server-key spend
    assert job.model.method == "json_schema"  # Sonnet 5.5 refuses forced tool choice
    sent_text = " ".join(str(m.content) for m in job.model.sent[0])
    assert "<coin>" in sent_text and '"source":"trend"' in sent_text and "key_levels" in sent_text
    [alert] = job.sent
    assert (
        alert.event == "brief_ready" and "Line 1." in alert.body and "BTC: lean long" in alert.body
    )
    assert alert.url == "https://crypto-desk-a9f.pages.dev"


def test_a_rerun_fills_gaps_and_last_week_gets_resolved(api_sessions, job) -> None:
    job.stance["ETH"] = "error"
    first = job.go(MON_19)
    assert first.status == "failed" and any("desk ETH: error" in p for p in first.problems)
    again = job.go(MON_19)  # only ETH's desk is missing; the brief exists
    assert job.calls == ["BTC", "ETH", "SOL", "ETH"]
    assert again.brief_note == "already written for this week" and len(job.sent) == 1
    job.stance.clear()
    job.go(MON_19)
    with api_sessions() as s:
        assert s.scalar(select(func.count()).select_from(Signal)) == 9
    nxt = job.go(MON_26)
    assert len(nxt.signals.resolved) == 9
    with api_sessions() as s:
        outcomes = s.scalars(select(SignalOutcome)).all()
        assert len(outcomes) == 9 and all(o.reference_close for o in outcomes)
        assert chain.verify(s) == []


def test_invalid_desk_signal_writes_no_desk_row(api_sessions, job) -> None:
    job.stance["SOL"] = "invalid"
    result = job.go(MON_26)
    assert result.status == "failed"
    assert "desk SOL: invalid (target too far.)" in result.problems
    with api_sessions() as s:
        assert (
            s.scalar(select(func.count()).where(Signal.coin == "SOL", Signal.source == "desk")) == 0
        )
        assert s.scalar(select(func.count()).where(Signal.coin == "SOL")) == 2  # the baselines


def test_dry_run_writes_nothing_but_reports_signals(api_sessions, job) -> None:
    result = job.go(MON_26, dry_run=True)
    assert result.status == "success" and result.run_id is None and result.brief is not None
    assert len(result.signals.all_signals()) == 9 and not result.signals.written
    assert "lean long" in result.summary() and "(not written)" in result.summary()
    assert job.sent == []
    with api_sessions() as s:
        for model in (Signal, Brief, JobRun, SignalOutcome):
            assert s.scalar(select(func.count()).select_from(model)) == 0


def test_watchlist_coins_are_capped_and_skipped_near_the_budget_cap(
    api_sessions, job, monkeypatch
) -> None:
    from desk.agents import cost

    with api_sessions.begin() as s:
        for i, sym in enumerate(("AAA", "BBB", "CCC", "DDD")):
            s.add(
                Coin(
                    symbol=sym,
                    name=sym,
                    source_market=f"{sym}/USD",
                    is_watchlist=True,
                    added_at=dt.datetime(2026, 10, 1 + i, tzinfo=dt.UTC),
                )
            )
    with api_sessions() as s:
        coins, skipped = signals_run.signal_coins(s, degraded=False, max_watchlist=3)
        assert coins == ["BTC", "ETH", "SOL", "AAA", "BBB", "CCC"] and skipped == ["DDD"]
        assert signals_run.signal_coins(s, degraded=True, max_watchlist=3)[0] == [
            "BTC",
            "ETH",
            "SOL",
        ]
    real = cost.budget
    monkeypatch.setattr(
        cost,
        "budget",
        lambda s, today=None: real(s, today).__class__(
            cap=real(s).cap, spent=real(s).cap * Decimal("0.9"), degrade_at=real(s).degrade_at
        ),
    )
    result = job.go(MON_26)
    assert result.signals is not None, result.error_detail
    assert result.signals.degraded and job.calls == ["BTC", "ETH", "SOL"]
    assert any("watchlist skipped (spend is near the cap)" in n for n in result.signals.notes)
    assert result.brief is not None and result.brief.model == "claude-haiku-5-5"


def test_stale_coin_gets_no_signals(job, monkeypatch) -> None:
    real = signals_run.last_close
    monkeypatch.setattr(
        signals_run,
        "last_close",
        lambda s, coin, day: None if coin == "SOL" else real(s, coin, day),
    )
    result = job.go(MON_26, coins=["BTC", "ETH"])
    assert "stale: SOL has no candle for 2026-10-25" in result.problems
    assert job.calls == ["BTC", "ETH"]


def test_mco_rows_stay_out_of_the_public_summary(job) -> None:
    result = job.go(MON_26, dry_run=True)
    r = result.signals.runs["BTC"]
    r.signals.append(
        Proposed(
            coin="BTC",
            source="mco",
            stance="lean_long",
            confidence=0.7,
            invalidation=12345.0,
            target=23456.0,
        )
    )
    assert "12,345" not in result.summary() and "hidden: MCO-derived" in result.summary()
    assert "12,345" in result.summary(private=True)


# --- The brief writer ------------------------------------------------------------------------


def test_render_and_checks() -> None:
    b = brief_for(["BTC", "ETH"])
    md = brief_writer.render(dt.date(2026, 11, 2), b, "claude-sonnet-5-5")
    assert md.startswith("# Weekly brief: week of 2026-11-02")
    assert "- Line 5." in md and "## ETH" in md and "20W SMA 100.00" in md
    assert "Not financial advice" in md
    assert brief_writer.check(b, ["BTC", "ETH"]) == []
    assert brief_writer.check(b, ["BTC", "SOL"])  # wrong coins
    short = b.model_copy(update={"summary": ["one"]})
    assert brief_writer.check(short, ["BTC", "ETH"]) == ["summary has 1 lines, not 5"]


def test_brief_estimate() -> None:
    e = brief_writer.estimate(3, "claude-sonnet-5-5")
    assert e["tokens_in"] == 15_000 and e["tokens_out"] == 5_700
    assert e["cost_usd"] == pytest.approx(0.030 + 0.057)
