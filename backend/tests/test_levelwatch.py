"""The daily level watch (Stage 7.1, D51): crossings of signal and key levels by the close, one
alert per run, de-duplication by day, and MCO-derived crossings kept out of the public log."""

import datetime as dt

import pytest
from sqlalchemy import func, select

from desk.data import market
from desk.jobs import levelwatch
from desk.jobs.levelwatch import crossed, find_crossings, run_levelwatch
from desk.models import Coin, JobRun
from desk.signals import chain
from desk.signals.chain import Proposed

DAY = dt.date(2026, 10, 28)  # a Wednesday; its signal week starts 2026-10-26
NOW = dt.datetime(2026, 10, 29, 1, 0, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("prev", "close", "level", "expected"),
    [
        (99, 101, 100, "up"),
        (99, 100, 100, "up"),  # closing on the level counts
        (101, 99, 100, "down"),
        (101, 100, 100, "down"),
        (100, 101, 100, None),  # it was already there
        (99, 99.5, 100, None),
        (101, 102, 100, None),
    ],
)
def test_crossed(prev, close, level, expected) -> None:
    assert crossed(prev, close, level) == expected


def seed(pg_sessions, closes: list[float]) -> None:
    """BTC: flat at 100 for 300 days, then `closes` ending on DAY."""
    start = DAY - dt.timedelta(days=300 + len(closes) - 1)
    values = [100.0] * 300 + closes
    with pg_sessions.begin() as s:
        s.add(Coin(symbol="BTC", name="Bitcoin", source_market="BTC/USD"))
        s.flush()
        market.upsert_candles(
            s,
            [
                {
                    "coin": "BTC",
                    "date": start + dt.timedelta(days=i),
                    "open": c,
                    "high": c,
                    "low": c,
                    "close": c,
                    "volume": 1.0,
                    "source": "test",
                }
                for i, c in enumerate(values)
            ],
        )


def signals(pg_sessions, *rows: Proposed, week: dt.date = dt.date(2026, 10, 26)) -> None:
    with pg_sessions.begin() as s:
        chain.append(s, 1, week, list(rows))


def desk(**kw) -> Proposed:
    base = {
        "coin": "BTC",
        "source": "desk",
        "stance": "lean_long",
        "confidence": 0.6,
        "entry_low": 95.0,
        "entry_high": 98.0,
        "invalidation": 90.0,
        "target": 104.0,
    }
    return Proposed(**{**base, **kw})


def test_signal_levels_crossed_by_the_close(pg_sessions) -> None:
    seed(pg_sessions, [103.0, 105.0])
    signals(
        pg_sessions,
        desk(),
        Proposed(coin="BTC", source="trend", stance="lean_long", confidence=0.6, target=104.5),
    )
    with pg_sessions() as s:
        found, notes = find_crossings(s, DAY)
    assert notes == []
    by_source = [(c.source, c.label, c.direction) for c in found if c.source != "key"]
    assert by_source == [("desk", "target", "up")]  # trend rows aren't watched
    assert found[0].text() == "BTC closed above the desk's target 104.00 (103.00 -> 105.00)"


def test_key_levels_use_the_previous_day(pg_sessions) -> None:
    seed(pg_sessions, [110.0, 105.0, 120.0])  # a new all-time high
    with pg_sessions() as s:
        found, _ = find_crossings(s, DAY)
    ath = [c for c in found if c.label == "all-time high"]
    assert [c.level for c in ath] == [110.0]  # the ATH as of the day before, not the new one
    assert all(c.source == "key" and c.direction == "up" for c in found)


def test_only_this_weeks_signals_are_watched(pg_sessions) -> None:
    seed(pg_sessions, [103.0, 105.0])
    signals(pg_sessions, desk(), week=dt.date(2026, 10, 19))
    with pg_sessions() as s:
        found, _ = find_crossings(s, DAY)
    assert [c for c in found if c.source == "desk"] == []


def test_missing_candles_are_a_note(pg_sessions) -> None:
    with pg_sessions.begin() as s:
        s.add(Coin(symbol="BTC", name="Bitcoin", source_market="BTC/USD"))
    with pg_sessions() as s:
        assert find_crossings(s, DAY) == ([], ["BTC: no candles for 2026-10-27 and 2026-10-28"])


def test_one_alert_per_run_and_one_run_per_day(pg_sessions, monkeypatch) -> None:
    seed(pg_sessions, [103.0, 105.0])
    signals(
        pg_sessions,
        desk(),
        Proposed(
            coin="BTC",
            source="mco",
            stance="lean_long",
            confidence=0.7,
            invalidation=80.0,
            target=104.2,
        ),
    )
    sent = []
    monkeypatch.setattr(levelwatch, "send", lambda alert: sent.append(alert) or {"discord": "sent"})
    result = run_levelwatch(pg_sessions, NOW)
    assert result.status == "success" and len(sent) == 1
    [alert] = sent
    assert alert.event == "level_cross" and alert.title == "Level crossings on 2026-10-28"
    assert "the desk's target 104.00" in alert.body and "MCO's target 104.20" in alert.body
    public = result.summary()
    assert "104.20" not in public and "1 MCO-derived, hidden here" in public
    assert "104.20" in result.summary(private=True)
    again = run_levelwatch(pg_sessions, NOW + dt.timedelta(hours=2))
    assert again.skipped == "already ran for 2026-10-28" and len(sent) == 1
    run_levelwatch(pg_sessions, NOW, force=True)
    assert len(sent) == 2
    with pg_sessions() as s:
        assert s.scalar(select(func.count()).where(JobRun.job == "levelwatch")) == 2


def test_dry_run_sends_and_records_nothing(pg_sessions, monkeypatch) -> None:
    seed(pg_sessions, [103.0, 105.0])
    signals(pg_sessions, desk())
    monkeypatch.setattr(levelwatch, "send", lambda alert: pytest.fail("no alerts in a dry run"))
    result = run_levelwatch(pg_sessions, NOW, dry_run=True)
    assert result.crossings and result.run_id is None
    with pg_sessions() as s:
        assert s.scalar(select(func.count()).select_from(JobRun)) == 0
