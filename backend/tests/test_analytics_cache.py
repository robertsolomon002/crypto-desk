"""analytics_cache against Postgres: hits, fingerprint invalidation, refresh, CLI (Stage 1.3).

Needs TEST_DATABASE_URL (e.g. the docker-compose Postgres); skipped otherwise.
"""

import datetime as dt

import numpy as np
import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from desk.analytics import cache
from desk.cli import app
from desk.config import get_settings
from desk.data import market
from desk.data.coins import seed_coins
from desk.models import AnalyticsCache

D = dt.date


def candles(coin: str, start: D, days: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, days)))
    return [
        {"coin": coin, "date": start + dt.timedelta(days=i), "open": c, "high": c * 1.01,
         "low": c * 0.99, "close": c, "volume": 1.0, "source": "coinbase"}
        for i, c in enumerate(closes.tolist())
    ]  # fmt: skip


@pytest.fixture
def loaded(pg_sessions):
    with pg_sessions.begin() as s:
        seed_coins(s)
        market.upsert_candles(s, candles("BTC", D(2024, 1, 1), 200, 1))
        market.upsert_candles(s, candles("ETH", D(2024, 1, 1), 200, 2))
    return pg_sessions


def rows(sessions) -> int:
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(AnalyticsCache))


def test_hit_then_invalidated_by_a_corrected_close(loaded) -> None:
    with loaded.begin() as s:
        first, hit = cache.get_or_compute(s, "drawdown_episodes", "BTC")
    assert not hit and first
    with loaded.begin() as s:
        again, hit = cache.get_or_compute(s, "drawdown_episodes", "btc")
    assert hit and again == first

    # Correct one close without changing the date range or row count
    fix = candles("BTC", D(2024, 1, 1), 200, 1)[100]
    fix["close"] = fix["close"] * 0.5
    with loaded.begin() as s:
        market.upsert_candles(s, [fix])
    with loaded.begin() as s:
        changed, hit = cache.get_or_compute(s, "drawdown_episodes", "BTC")
    assert not hit and changed != first
    assert rows(loaded) == 1  # same key: the row was overwritten


def test_new_day_and_params_get_their_own_rows(loaded) -> None:
    with loaded.begin() as s:
        cache.get_or_compute(s, "return_distribution", "BTC")
        cache.get_or_compute(s, "return_distribution", "BTC", horizon="1d")
        _, hit = cache.get_or_compute(s, "return_distribution", "BTC", as_of=D(2024, 3, 1))
    assert not hit and rows(loaded) == 3
    with loaded.begin() as s:
        market.upsert_candles(s, candles("BTC", D(2024, 1, 1), 201, 1)[-1:])
        _, hit = cache.get_or_compute(s, "return_distribution", "BTC")
    assert not hit and rows(loaded) == 4  # keyed by the new last date


def test_refresh_fills_then_hits(loaded) -> None:
    with loaded.begin() as s:
        first = cache.refresh(s)
    with loaded.begin() as s:
        second = cache.refresh(s)
    assert first["computed"] > 0 and first["cached"] == 0  # SOL has no candles: skipped
    assert second == {"computed": 0, "cached": first["computed"], "pruned": 0}


def test_cli_show_and_cached(loaded, pg_engine, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        shown = runner.invoke(app, ["analytics", "show", "levels", "BTC"])
        listed = runner.invoke(app, ["analytics", "list"])
        bad = runner.invoke(app, ["analytics", "show", "nope", "BTC"])
        first = runner.invoke(app, ["analytics", "show", "yoy", "ETH", "--cached"])
        second = runner.invoke(app, ["analytics", "show", "yoy", "ETH", "--cached"])
    finally:
        get_settings.cache_clear()
    assert shown.exit_code == 0, shown.output
    assert "prev_week_high" in shown.output and "ath" in shown.output
    assert "cycles_day_n" in listed.output and "mode=halving" in listed.output
    assert bad.exit_code != 0
    assert "computed and cached" in first.output and "cache hit" in second.output
