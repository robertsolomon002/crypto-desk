"""Market data without a database: pagination, closed candles, retries, resampling, validation."""

import datetime as dt
import itertools
import json

import ccxt
import httpx
import pandas as pd
import pytest
import respx

from desk.data import coinmetrics, market
from tests.conftest import FIXTURES
from tests.market_fakes import FakeExchange, make_candles, ms

D = dt.date


def frame(rows: list[tuple]) -> pd.DataFrame:
    """rows: (date, open, high, low, close, volume)"""
    return market.to_frame(
        [
            {"date": d, "open": o, "high": h, "low": lo, "close": c, "volume": v, "source": "x"}
            for d, o, h, lo, c, v in rows
        ]
    )


def daily_range(first: D, last: D, start: float = 100.0) -> pd.DataFrame:
    return frame([(market._to_date(c[0]), *c[1:]) for c in make_candles(first, last, start)])


# --- fetch_daily ------------------------------------------------------------------------------


def test_pagination_walks_windows_and_dedupes_overlaps() -> None:
    candles = make_candles(D(2015, 7, 20), D(2016, 12, 31))
    ex = FakeExchange(candles)
    now = dt.datetime(2017, 1, 1, tzinfo=dt.UTC)
    out = market.fetch_daily(ex, "BTC/USD", D(2010, 1, 1), now=now)
    assert [c[0] for c in out] == [c[0] for c in candles]  # all days, once each, in order
    assert len(ex.calls) > 2  # several 300-day windows, including empty ones before 2015
    assert all(b - a == market.WINDOW * market.DAY_MS for a, b in itertools.pairwise(ex.calls))


def test_only_closed_candles_are_kept() -> None:
    ex = FakeExchange(make_candles(D(2024, 1, 1), D(2024, 1, 10)))
    now = dt.datetime(2024, 1, 10, 12, 0, tzinfo=dt.UTC)  # Jan 10 is still in progress
    out = market.fetch_daily(ex, "BTC/USD", D(2024, 1, 1), now=now)
    assert out[-1][0] == ms(D(2024, 1, 9))
    # exactly at midnight, the previous day has just closed
    out = market.fetch_daily(
        ex, "BTC/USD", D(2024, 1, 1), now=dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
    )
    assert out[-1][0] == ms(D(2024, 1, 9))


def test_nothing_to_fetch_when_up_to_date() -> None:
    ex = FakeExchange(make_candles(D(2024, 1, 1), D(2024, 1, 10)))
    now = dt.datetime(2024, 1, 10, 6, tzinfo=dt.UTC)
    assert market.fetch_daily(ex, "BTC/USD", D(2024, 1, 10), now=now) == []
    assert ex.calls == []


def test_retries_network_errors_then_succeeds() -> None:
    ex = FakeExchange(make_candles(D(2024, 1, 1), D(2024, 1, 5)), fail_first=2)
    sleeps: list[float] = []
    now = dt.datetime(2024, 1, 6, tzinfo=dt.UTC)
    out = market.fetch_daily(ex, "BTC/USD", D(2024, 1, 1), now=now, sleep=sleeps.append)
    assert len(out) == 5
    assert sleeps == [2.0, 4.0]


def test_gives_up_after_three_attempts() -> None:
    ex = FakeExchange(make_candles(D(2024, 1, 1), D(2024, 1, 5)), fail_first=3)
    now = dt.datetime(2024, 1, 6, tzinfo=dt.UTC)
    with pytest.raises(ccxt.NetworkError):
        market.fetch_daily(ex, "BTC/USD", D(2024, 1, 1), now=now, sleep=lambda _: None)


# --- Coin Metrics -----------------------------------------------------------------------------


@respx.mock
def test_coinmetrics_follows_next_page_url() -> None:
    pages = json.loads((FIXTURES / "coinmetrics_btc_priceusd.json").read_text(encoding="utf-8"))
    route = respx.get(f"{coinmetrics.BASE_URL}/timeseries/asset-metrics").mock(
        side_effect=[
            httpx.Response(200, json=pages["page1"]),
            httpx.Response(200, json=pages["page2"]),
        ]
    )
    with coinmetrics.make_client() as client:
        points = coinmetrics.fetch_asset_metric(
            client, "btc", "PriceUSD", D(2010, 7, 18), D(2010, 7, 22)
        )
    assert route.call_count == 2
    assert "next_page_token" in str(route.calls[1].request.url)
    assert [d for d, _ in points] == [D(2010, 7, 18) + dt.timedelta(days=i) for i in range(5)]
    assert points[0][1] == pytest.approx(0.08584)


# --- resample_weekly --------------------------------------------------------------------------


def test_weeks_start_monday_and_span_year_boundary() -> None:
    daily = daily_range(D(2024, 12, 23), D(2025, 1, 12))  # Mon 2024-12-23 .. Sun 2025-01-12
    w = market.resample_weekly(daily)
    assert [ts.date() for ts in w.index] == [D(2024, 12, 23), D(2024, 12, 30), D(2025, 1, 6)]
    assert all(ts.day_of_week == 0 for ts in w.index)
    # the week of 2024-12-30 covers Dec 30 .. Jan 5 (days 7..13 of the series)
    row = w.loc[pd.Timestamp("2024-12-30", tz="UTC")]
    assert row["open"] == 107 - 0.5
    assert row["close"] == 113
    assert row["high"] == 113 + 1.0
    assert row["low"] == 107 - 1.0
    assert row["volume"] == sum(10.0 + i for i in range(7, 14))


def test_week_across_month_boundary() -> None:
    daily = daily_range(D(2024, 1, 29), D(2024, 2, 4))  # Mon Jan 29 .. Sun Feb 4
    w = market.resample_weekly(daily)
    assert len(w) == 1
    assert w.index[0].date() == D(2024, 1, 29)
    assert w.iloc[0]["close"] == 106


def test_partial_weeks_dropped_unless_requested() -> None:
    daily = daily_range(D(2024, 1, 3), D(2024, 1, 24))  # Wed .. Wed
    assert [ts.date() for ts in market.resample_weekly(daily).index] == [
        D(2024, 1, 8),
        D(2024, 1, 15),
    ]
    partial = market.resample_weekly(daily, include_partial=True)
    assert [ts.date() for ts in partial.index] == [
        D(2024, 1, 1), D(2024, 1, 8), D(2024, 1, 15), D(2024, 1, 22)
    ]  # fmt: skip


def test_close_only_days_use_close_for_ohlc() -> None:
    rows = [
        (D(2013, 1, 7) + dt.timedelta(days=i), None, None, None, 10.0 + i, None) for i in range(7)
    ]
    w = market.resample_weekly(frame(rows))
    assert w.iloc[0][["open", "high", "low", "close"]].tolist() == [10.0, 16.0, 10.0, 16.0]


def test_resample_empty() -> None:
    assert market.resample_weekly(frame([])).empty


# --- validate ---------------------------------------------------------------------------------


def test_clean_data_has_no_issues() -> None:
    assert market.validate(daily_range(D(2024, 1, 1), D(2024, 3, 1))) == []


def test_validate_flags_every_kind() -> None:
    rows = [
        (D(2024, 1, 1), 100, 101, 99, 100, 1),
        (D(2024, 1, 2), 100, 101, 99, 100, 1),
        (D(2024, 1, 2), 100, 101, 99, 100, 1),  # duplicate
        (D(2024, 1, 5), 100, 101, 99, 150, 1),  # gap (3rd, 4th) + big move + close > high
        (D(2024, 1, 6), 150, 151, 152, 150, 1),  # low > high
        (D(2024, 1, 7), None, None, None, 140, None),  # close-only row: fine
    ]
    issues = market.validate(frame(rows))
    kinds = {(i.kind, i.date) for i in issues}
    assert ("duplicate", D(2024, 1, 2)) in kinds
    assert ("gap", D(2024, 1, 3)) in kinds
    assert ("big_move", D(2024, 1, 5)) in kinds
    assert ("ohlc", D(2024, 1, 5)) in kinds
    assert ("ohlc", D(2024, 1, 6)) in kinds
    assert not any(i.date == D(2024, 1, 7) for i in issues)
    gap = next(i for i in issues if i.kind == "gap")
    assert gap.detail.startswith("2 missing day(s)")


def test_big_move_threshold_is_strictly_over_40_percent() -> None:
    rows = [(D(2024, 1, 1), 100, 100, 100, 100, 1), (D(2024, 1, 2), 140, 140, 140, 140, 1)]
    assert market.validate(frame(rows)) == []


# --- live (RUN_LIVE=1) ------------------------------------------------------------------------


@pytest.mark.live
def test_live_coinbase_recent_days() -> None:
    since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=5)
    out = market.fetch_daily(market.make_exchange(), "BTC/USD", since)
    assert 4 <= len(out) <= 5


@pytest.mark.live
def test_live_coinmetrics_first_btc_price() -> None:
    with coinmetrics.make_client() as client:
        points = coinmetrics.fetch_asset_metric(
            client, "btc", "PriceUSD", D(2010, 1, 1), D(2010, 7, 20)
        )
    assert points[0][0] == D(2010, 7, 18)
