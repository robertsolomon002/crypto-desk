"""Market data against Postgres: migration, coin seeding, idempotent upserts, incremental updates.

Needs TEST_DATABASE_URL (e.g. the docker-compose Postgres); skipped otherwise.
"""

import datetime as dt
import json

import httpx
import pytest
import respx
from sqlalchemy import func, select
from typer.testing import CliRunner

from desk.cli import app
from desk.config import get_settings
from desk.data import coinmetrics, market
from desk.data.coins import active_coins, seed_coins
from desk.models import CandleDaily, Coin
from tests.conftest import FIXTURES
from tests.market_fakes import FakeExchange, make_candles

D = dt.date
UTC = dt.UTC


@pytest.fixture
def coins(pg_sessions):
    with pg_sessions.begin() as s:
        seed_coins(s)
    with pg_sessions() as s:
        return {c.symbol: c for c in active_coins(s)}


def count(sessions, **where) -> int:
    with sessions() as s:
        q = select(func.count()).select_from(CandleDaily)
        for k, v in where.items():
            q = q.where(getattr(CandleDaily, k) == v)
        return s.scalar(q)


def test_seed_coins_is_idempotent_and_flags_watchlist(pg_sessions, tmp_path) -> None:
    cfg = tmp_path / "coins.yaml"
    cfg.write_text(
        "max_watchlist: 10\n"
        "core:\n  - {symbol: BTC, name: Bitcoin, aliases: [btc], source_market: BTC/USD}\n"
        "watchlist:\n  - {symbol: LINK, name: Chainlink, source_market: LINK/USD}\n",
        encoding="utf-8",
    )
    for _ in range(2):
        with pg_sessions.begin() as s:
            assert seed_coins(s, cfg) == 2
    with pg_sessions() as s:
        rows = {c.symbol: c for c in s.scalars(select(Coin))}
    assert set(rows) == {"BTC", "LINK"}
    assert rows["LINK"].is_watchlist and not rows["BTC"].is_watchlist
    assert rows["BTC"].aliases == ["btc"] and rows["LINK"].aliases == []


def test_repo_coins_yaml_seeds_core_coins(coins) -> None:
    assert list(coins) == ["BTC", "ETH", "SOL"]
    assert coins["SOL"].source_market == "SOL/USD"


def test_upsert_is_idempotent_and_updates_win(pg_sessions, coins) -> None:
    rows = [
        {"coin": "ETH", "date": D(2024, 1, d), "open": 1.0, "high": 2.0, "low": 0.5,
         "close": 1.5, "volume": 3.0, "source": "coinbase"}
        for d in range(1, 6)
    ]  # fmt: skip
    with pg_sessions.begin() as s:
        assert market.upsert_candles(s, rows) == 5
    rows[-1] = {**rows[-1], "close": 1.75}
    with pg_sessions.begin() as s:
        assert market.upsert_candles(s, rows) == 0
    assert count(pg_sessions, coin="ETH") == 5
    with pg_sessions() as s:
        assert s.get(CandleDaily, ("ETH", D(2024, 1, 5))).close == 1.75


def test_incremental_update_refetches_only_the_overlap(pg_sessions, coins) -> None:
    ex = FakeExchange(make_candles(D(2021, 6, 17), D(2024, 1, 31)))
    with pg_sessions.begin() as s:
        added = market.update_coin(s, coins["SOL"], ex, now=dt.datetime(2024, 1, 20, tzinfo=UTC))
    assert added == {"coinbase": (D(2024, 1, 19) - D(2021, 6, 17)).days + 1}

    ex.calls.clear()
    with pg_sessions.begin() as s:
        added = market.update_coin(s, coins["SOL"], ex, now=dt.datetime(2024, 1, 25, tzinfo=UTC))
    assert added == {"coinbase": 5}  # Jan 20 .. Jan 24
    assert ex.calls[0] == market._to_ms(D(2024, 1, 19) - dt.timedelta(days=market.OVERLAP_DAYS))
    assert len(ex.calls) == 1

    with pg_sessions.begin() as s:  # same `now` again: nothing new
        assert market.update_coin(
            s, coins["SOL"], ex, now=dt.datetime(2024, 1, 25, tzinfo=UTC)
        ) == {"coinbase": 0}


@respx.mock
def test_btc_backfill_from_coinmetrics_before_first_coinbase_day(pg_sessions, coins) -> None:
    pages = json.loads((FIXTURES / "coinmetrics_btc_priceusd.json").read_text(encoding="utf-8"))
    # Coinbase "starts" 2010-07-21 here, so only Jul 18-20 should come from Coin Metrics
    route = respx.get(f"{coinmetrics.BASE_URL}/timeseries/asset-metrics").mock(
        side_effect=[
            httpx.Response(200, json=pages["page1"]),
            httpx.Response(200, json=pages["page2"]),
        ]
    )
    ex = FakeExchange(make_candles(D(2010, 7, 21), D(2010, 8, 31)))
    now = dt.datetime(2010, 9, 1, tzinfo=UTC)
    with coinmetrics.make_client() as cm, pg_sessions.begin() as s:
        added = market.update_coin(s, coins["BTC"], ex, cm, now=now)
    assert added == {"coinbase": 42, "coinmetrics": 3}
    assert "end_time=2010-07-20" in str(route.calls[0].request.url)

    with pg_sessions() as s:
        df = market.load_daily(s, "BTC")
        early = s.get(CandleDaily, ("BTC", D(2010, 7, 18)))
    assert (
        early.source == "coinmetrics"
        and early.open is None
        and early.close == pytest.approx(0.08584)
    )
    assert df.index[0].date() == D(2010, 7, 18)
    assert df.loc[df.source == "coinbase"].index[0].date() == D(2010, 7, 21)

    with coinmetrics.make_client() as cm, pg_sessions.begin() as s:  # backfill runs only once
        added = market.update_coin(s, coins["BTC"], ex, cm, now=now)
    assert "coinmetrics" not in added
    assert route.call_count == 2


def test_load_daily_respects_as_of(pg_sessions, coins) -> None:
    ex = FakeExchange(make_candles(D(2024, 1, 1), D(2024, 1, 31)))
    with pg_sessions.begin() as s:
        market.update_coin(s, coins["ETH"], ex, now=dt.datetime(2024, 2, 1, tzinfo=UTC))
    with pg_sessions() as s:
        df = market.load_daily(s, "ETH", as_of=D(2024, 1, 15))
    assert df.index.max().date() == D(2024, 1, 15)
    assert str(df.index.tz) == "UTC"


def test_cli_status(pg_sessions, pg_engine, coins, monkeypatch) -> None:
    ex = FakeExchange(make_candles(D(2024, 1, 1), D(2024, 1, 10)))
    with pg_sessions.begin() as s:
        market.update_coin(s, coins["ETH"], ex, now=dt.datetime(2024, 1, 11, tzinfo=UTC))
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(app, ["data", "status"])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    assert "ETH: 2024-01-01 -> 2024-01-10" in result.output
    assert "coinbase 10" in result.output
    assert "BTC: no candles" in result.output
