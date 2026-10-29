"""Context sources against Postgres: incremental, idempotent updates and as-of reads (Stage 1.2).

Needs TEST_DATABASE_URL (e.g. the docker-compose Postgres); skipped otherwise.
"""

import datetime as dt
import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from desk.cli import app
from desk.config import get_settings
from desk.data import calendar as cal
from desk.data import coinmetrics, dominance, fred, news, sentiment, series
from tests.conftest import FIXTURES

D = dt.date
UTC = dt.UTC
CM_URL = f"{coinmetrics.BASE_URL}/timeseries/asset-metrics"
FRED_URL = f"{fred.BASE_URL}/series/observations"
ALIASES = {"BTC": ["bitcoin", "btc"], "ETH": ["ethereum", "eth", "ether"], "SOL": ["solana", "sol"]}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def at(day: D, hour: int = 12) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def test_series_upsert_is_idempotent_and_load_applies_as_of_and_lag(pg_sessions) -> None:
    pts = [(D(2024, 1, d), float(d)) for d in range(1, 11)]
    with pg_sessions.begin() as s:
        assert series.upsert_series(s, "x", pts, "test") == 10
        assert series.upsert_series(s, "x", [(D(2024, 1, 10), 99.0)], "test") == 0
        assert series.upsert_series(s, "y", pts[:3], "test") == 3
    with pg_sessions() as s:
        assert series.last_date(s, "x") == D(2024, 1, 10)
        assert series.last_date(s, "nope") is None
        full = series.load_series(s, ["x", "y"])
        cut = series.load_series(s, ["x", "y"], as_of=D(2024, 1, 5), lag_days={"x": 2})
        empty = series.load_series(s, ["nope"])
    assert full.loc["2024-01-10", "x"] == 99.0 and str(full.index.tz) == "UTC"
    assert cut["x"].dropna().index.max().date() == D(2024, 1, 3)  # 2-day lag
    assert cut["y"].dropna().index.max().date() == D(2024, 1, 3)  # y only has 3 days
    assert list(empty.columns) == ["nope"] and empty.empty


@respx.mock
def test_fng_full_history_then_incremental(pg_sessions) -> None:
    ok = httpx.Response(200, json=fixture("fng.json"))
    route = respx.get(sentiment.URL).mock(return_value=ok)
    with httpx.Client() as client:
        with pg_sessions.begin() as s:
            assert sentiment.update(s, client, at(D(2026, 10, 29))) == 5
        assert route.calls[0].request.url.params["limit"] == "0"
        with pg_sessions.begin() as s:
            assert sentiment.update(s, client, at(D(2026, 10, 31))) == 0
        assert route.calls[1].request.url.params["limit"] == str(2 + sentiment.OVERLAP_DAYS)
    with pg_sessions() as s:
        assert len(sentiment.load_fng(s)) == 5
        cut = sentiment.load_fng(s, as_of=D(2026, 10, 27))
    assert cut.index.max().date() == D(2026, 10, 27) and len(cut) == 3


@respx.mock
def test_onchain_first_load_then_incremental_closed_days_only(pg_sessions) -> None:
    pages = fixture("coinmetrics_eth_metrics.json")
    route = respx.get(CM_URL).mock(
        side_effect=[
            httpx.Response(200, json=pages["page1"]),
            httpx.Response(200, json=pages["page2"]),
        ]
    )
    with coinmetrics.make_client() as cm, pg_sessions.begin() as s:
        added = coinmetrics.update_onchain(s, cm, "ETH", at(D(2022, 9, 18)))
    params = route.calls[0].request.url.params
    assert params["start_time"] == "2009-01-01" and params["end_time"] == "2022-09-17"
    assert added == {"CapMrktCurUSD": 6, "CapMVRVCur": 6, "SplyCur": 6, "AdrActCnt": 6,
                     "HashRate": 3}  # fmt: skip

    # Next run: one request from (latest day - 3), ignoring that HashRate stopped on 09-14.
    # The source also returns "today" (09-20), which is not closed yet and must be dropped.
    rows = [
        {"asset": "eth", "time": f"2022-09-{d}T00:00:00.000000000Z", "CapMVRVCur": "0.9",
         "CapMrktCurUSD": "1", "SplyCur": "1", "AdrActCnt": "1", "HashRate": None}
        for d in range(14, 21)
    ]  # fmt: skip
    route.side_effect = [httpx.Response(200, json={"data": rows})]
    with coinmetrics.make_client() as cm, pg_sessions.begin() as s:
        added = coinmetrics.update_onchain(s, cm, "ETH", at(D(2022, 9, 20)))
    params = route.calls[-1].request.url.params
    assert params["start_time"] == "2022-09-14" and params["end_time"] == "2022-09-19"
    assert route.call_count == 3
    assert added["CapMVRVCur"] == 2 and added["HashRate"] == 0  # 09-18, 09-19

    with pg_sessions() as s:
        df = coinmetrics.load_onchain(s, "ETH")
        cut = coinmetrics.load_onchain(s, "ETH", as_of=D(2022, 9, 15))
    assert list(df.columns) == coinmetrics.METRICS
    assert df.index.max().date() == D(2022, 9, 19)
    assert df.loc["2022-09-17", "CapMVRVCur"] == 0.9  # overlap days were refreshed
    assert cut.index.max().date() == D(2022, 9, 15)
    assert cut["HashRate"].dropna().index.max().date() == D(2022, 9, 14)


@respx.mock
def test_fred_update_and_release_lag_as_of(pg_sessions) -> None:
    bodies = fixture("fred_observations.json")
    route = respx.get(FRED_URL).mock(
        side_effect=lambda req: httpx.Response(200, json=bodies[req.url.params["series_id"]])
    )
    cfg = [
        fred.FredSeries("DGS10", "10y", "percent", 6),
        fred.FredSeries("M2SL", "M2", "billions USD", 60),
    ]
    with fred.make_client() as client, pg_sessions.begin() as s:
        added = fred.update(s, client, "k", at(D(2026, 10, 29)), cfg)
    assert added == {"DGS10": 7, "M2SL": 5}
    assert route.calls[0].request.url.params["observation_start"] == "2010-01-01"

    with fred.make_client() as client, pg_sessions.begin() as s:
        assert fred.update(s, client, "k", at(D(2026, 10, 29)), cfg) == {"DGS10": 0, "M2SL": 0}
    assert route.calls[2].request.url.params["observation_start"] == "2024-12-31"  # last - 365

    with pg_sessions() as s:
        df = fred.load_macro(s, config=cfg)
        cut = fred.load_macro(s, as_of=D(2026, 9, 15), config=cfg)
        dec = fred.load_macro(s, as_of=D(2025, 12, 31), config=cfg)
    assert list(df.columns) == ["DGS10", "M2SL"]
    # M2SL for July (dated 07-01) is known from 08-30; August (08-01) only from 09-30
    assert cut["M2SL"].dropna().index.max().date() == D(2026, 7, 1)
    # DGS10 for 12-24 is known from 12-30; 12-26 not until 2026-01-01
    assert dec["DGS10"].dropna().index.max().date() == D(2025, 12, 24)


@respx.mock
def test_dominance_snapshot_once_per_day(pg_sessions) -> None:
    body = fixture("coingecko_global.json")
    route = respx.get(f"{dominance.BASE_URL}/global")
    route.mock(return_value=httpx.Response(200, json=body))
    with dominance.make_client("demo-key") as client:
        with pg_sessions.begin() as s:
            assert dominance.update(s, client) == {"btc": 1, "eth": 1}
        body["data"]["market_cap_percentage"]["btc"] = 60.0
        route.return_value = httpx.Response(200, json=body)
        with pg_sessions.begin() as s:
            assert dominance.update(s, client) == {"btc": 0, "eth": 0}
    assert route.calls[0].request.headers["x-cg-demo-api-key"] == "demo-key"
    with pg_sessions() as s:
        df = dominance.load_dominance(s)
        before = dominance.load_dominance(s, as_of=D(2026, 10, 28))
    assert df.loc["2026-10-29", "btc"] == 60.0  # the later snapshot wins
    assert before.empty


@respx.mock
def test_news_update_dedupes_across_runs_and_as_of(pg_sessions) -> None:
    content = (FIXTURES / "rss_sample.xml").read_bytes()
    respx.get("https://a.example/rss").mock(return_value=httpx.Response(200, content=content))
    feeds = [news.Feed("A", "https://a.example/rss")]
    now = at(D(2026, 10, 29))
    with httpx.Client() as client:
        with pg_sessions.begin() as s:
            assert news.update(s, client, ALIASES, now, feeds) == (4, [])
        with pg_sessions.begin() as s:
            assert news.update(s, client, ALIASES, now, feeds) == (0, [])
    # Same headline under another URL from another source: dropped by title
    copy = news.NewsItem("B", "Solana Validators Ship Upgrade", "https://b.example/x", now, ())
    with pg_sessions.begin() as s:
        assert news.store(s, [copy]) == 0

    with pg_sessions() as s:
        latest = news.load_news(s)
        oct26 = news.load_news(s, as_of=D(2026, 10, 26))
        sol = news.load_news(s, coin="sol")
    assert len(latest) == 4 and latest[0]["published_at"] == now
    assert [n["title"] for n in oct26] == ["Solar power and soldiers: a macro story"]
    assert [n["title"] for n in sol] == ["Solana validators ship upgrade"]


def test_calendar_sync_matches_yaml_and_as_of_window(pg_sessions, tmp_path) -> None:
    with pg_sessions.begin() as s:
        assert cal.sync(s) == (25, 0)
    with pg_sessions.begin() as s:
        assert cal.sync(s) == (25, 0)  # idempotent
    with pg_sessions() as s:
        week = cal.load_events(s, D(2026, 12, 7))
        fomc = cal.load_events(s, D(2026, 10, 1), days_ahead=90, kinds=["fomc"])
    assert [(e["date"], e["kind"]) for e in week] == [(D(2026, 12, 9), "fomc"),
                                                      (D(2026, 12, 10), "cpi")]  # fmt: skip
    assert week[0]["time_utc"] == dt.time(19, 0)
    assert [e["date"] for e in fomc] == [D(2026, 10, 28), D(2026, 12, 9)]

    path = tmp_path / "calendar.yaml"
    path.write_text(
        'events:\n  - {date: 2026-12-09, time_utc: "19:30", kind: fomc, '
        "title: FOMC rate decision (with SEP), source: https://www.federalreserve.gov/x}\n",
        encoding="utf-8",
    )
    with pg_sessions.begin() as s:
        assert cal.sync(s, path) == (1, 24)
    with pg_sessions() as s:
        (only,) = cal.load_events(s, D(2026, 12, 9))
    assert only["time_utc"] == dt.time(19, 30) and only["source_url"].endswith("/x")


@pytest.fixture
def cli_env(pg_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("FRED_API_KEY", "test-fred-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
def test_cli_update_runs_selected_sources_and_reports_failures(pg_sessions, cli_env) -> None:
    respx.get(FRED_URL).mock(return_value=httpx.Response(200, json={"observations": [
        {"date": "2026-10-01", "value": "1.5"}]}))  # fmt: skip
    fng = respx.get(sentiment.URL).mock(return_value=httpx.Response(500))
    result = CliRunner().invoke(app, ["data", "update", "--sentiment", "--macro", "--calendar"])
    assert result.exit_code == 1
    assert "sentiment:\n  FAILED: HTTPStatusError" in result.output
    assert "DTWEXBGS +1" in result.output and "M2SL +1" in result.output  # others still ran
    assert "25 events in calendar.yaml" in result.output
    assert "Failed sources: sentiment" in result.output
    assert "test-fred-key" not in result.output

    fng.return_value = httpx.Response(200, json=fixture("fng.json"))
    result = CliRunner().invoke(app, ["data", "update", "--sentiment"])
    assert result.exit_code == 0, result.output
    assert "fng +" in result.output

    result = CliRunner().invoke(app, ["data", "status"])
    assert result.exit_code == 0, result.output
    assert "fred:DGS10: 2026-10-01 -> 2026-10-01" in result.output
    assert "news: 0 headlines" in result.output
    assert "calendar: next" in result.output
