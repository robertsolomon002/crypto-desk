"""Context sources without a database: parsing recorded responses, cleaning untrusted headlines,
coin tagging, FRED error redaction and the repo's calendar.yaml (Stage 1.2)."""

import datetime as dt
import json

import httpx
import pytest
import respx

from desk.config import get_settings
from desk.data import calendar as cal
from desk.data import coinmetrics, dominance, fred, http, news, sentiment
from tests.conftest import FIXTURES

D = dt.date
UTC = dt.UTC
NOW = dt.datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
ALIASES = {
    "BTC": ["bitcoin", "btc", "xbt"],
    "ETH": ["ethereum", "eth", "ether"],
    "SOL": ["solana", "sol"],
}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- Fear & Greed -----------------------------------------------------------------------------


def test_fng_parse_is_oldest_first_with_utc_dates() -> None:
    points = sentiment.parse(fixture("fng.json"))
    assert len(points) == 5
    assert points == sorted(points)
    assert points[-1] == (D(2026, 10, 29), 51.0)  # timestamp 1793232000 = 2026-10-29 00:00 UTC
    assert all(0 <= v <= 100 for _, v in points)


def test_fng_parse_raises_on_api_error() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        sentiment.parse({"data": [], "metadata": {"error": "boom"}})


# --- Coin Metrics -----------------------------------------------------------------------------


@respx.mock
def test_coinmetrics_multi_metric_follows_pages_and_skips_nulls() -> None:
    pages = fixture("coinmetrics_eth_metrics.json")
    route = respx.get(f"{coinmetrics.BASE_URL}/timeseries/asset-metrics").mock(
        side_effect=[
            httpx.Response(200, json=pages["page1"]),
            httpx.Response(200, json=pages["page2"]),
        ]
    )
    with coinmetrics.make_client() as client:
        out = coinmetrics.fetch_asset_metrics(
            client, "eth", coinmetrics.METRICS, D(2022, 9, 12), D(2022, 9, 17)
        )
    assert route.call_count == 2
    first = str(route.calls[0].request.url)
    assert "metrics=CapMrktCurUSD%2CCapMVRVCur" in first and "end_time=2022-09-17" in first
    assert "next_page_token=PAGE2" in str(route.calls[1].request.url)
    assert [d for d, _ in out["CapMVRVCur"]] == [D(2022, 9, d) for d in range(12, 18)]
    # The Merge: ETH hash rate is null from 2022-09-15
    assert [d for d, _ in out["HashRate"]] == [D(2022, 9, 12), D(2022, 9, 13), D(2022, 9, 14)]
    assert out["CapMVRVCur"][1] == (D(2022, 9, 13), pytest.approx(0.922054273893))


# --- FRED -------------------------------------------------------------------------------------


@respx.mock
def test_fred_observations_skip_missing_values() -> None:
    body = fixture("fred_observations.json")["DGS10"]
    route = respx.get(f"{fred.BASE_URL}/series/observations")
    route.mock(return_value=httpx.Response(200, json=body))
    with fred.make_client() as client:
        points = fred.fetch_observations(client, "DGS10", "k", D(2025, 12, 22))
    assert D(2025, 12, 25) not in {d for d, _ in points}  # "." on Christmas
    assert points[0] == (D(2025, 12, 22), 4.17) and len(points) == 7


@respx.mock
def test_fred_errors_never_contain_the_api_key() -> None:
    respx.get(f"{fred.BASE_URL}/series/observations").mock(
        return_value=httpx.Response(400, json={"error_message": "bad"})
    )
    with fred.make_client() as client, pytest.raises(fred.FredError) as info:
        fred.fetch_observations(client, "DGS10", "SECRET-CANARY-KEY", D(2025, 1, 1))
    assert "SECRET-CANARY-KEY" not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert str(info.value) == "FRED DGS10: HTTP 400"


def test_repo_fred_config_has_release_lags() -> None:
    cfg = {s.id: s for s in fred.load_config()}
    assert set(cfg) == {"DTWEXBGS", "DGS10", "DFF", "M2SL"}
    assert cfg["M2SL"].release_lag_days >= 58 and cfg["DGS10"].release_lag_days >= 1
    assert cfg["DGS10"].key == "fred:DGS10"


# --- CoinGecko dominance ----------------------------------------------------------------------


def test_dominance_parse_uses_updated_at_utc_day() -> None:
    day, values = dominance.parse_global(fixture("coingecko_global.json"))
    assert day == D(2026, 10, 29)
    assert set(values) == {"btc", "eth"}
    assert 0 < values["eth"] < values["btc"] < 100


# --- News -------------------------------------------------------------------------------------


def test_clean_text_strips_html_scripts_entities_and_controls() -> None:
    raw = "<p>Bitcoin &amp; <b>ether</b>\x00\x1b[31m<script>alert(1)</script>  rally</p>"
    assert news.clean_text(raw) == "Bitcoin & ether[31m rally"
    assert news.clean_text("<img src=x onerror=alert(1)>") == ""
    assert news.clean_text("a" * 400).endswith("…") and len(news.clean_text("a" * 400)) == 300
    assert news.clean_text(None) == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://x.com/a?utm_source=rss&id=7#frag", "https://x.com/a?id=7"),
        ("HTTPS://X.COM/Path?ref=feed", "https://x.com/Path"),
        ("javascript:alert(1)", None),
        ("data:text/html,hi", None),
        ("/relative/path", None),
        ("", None),
    ],
)
def test_clean_url(raw: str, expected: str | None) -> None:
    assert news.clean_url(raw) == expected


@pytest.mark.parametrize(
    ("text", "coins"),
    [
        ("Bitcoin and Ethereum rally", ("BTC", "ETH")),
        ("$SOL pumps; ETH/BTC ratio falls", ("BTC", "ETH", "SOL")),
        ("Solar stocks and soldiers", ()),
        ("Tether mints more USDT", ()),  # "ether" inside "Tether" is not a match
        ("XBT futures", ("BTC",)),
    ],
)
def test_tag_coins_whole_words_only(text: str, coins: tuple[str, ...]) -> None:
    assert news.tag_coins(text, news.alias_patterns(ALIASES)) == coins


def test_parse_feed_normalizes_and_drops_unsafe_items() -> None:
    content = (FIXTURES / "rss_sample.xml").read_bytes()
    items = news.parse_feed(content, "Example", news.alias_patterns(ALIASES), NOW)
    by_title = {i.title: i for i in items}
    assert len(items) == 5  # javascript: link and the undated item are dropped
    top = by_title["Bitcoin tops $100K & ether follows"]
    assert top.url == "https://news.example.com/markets/btc-100k?id=7"
    assert top.coins == ("BTC", "ETH")
    assert top.published_at == dt.datetime(2026, 10, 27, 14, 30, tzinfo=UTC)
    sol = by_title["Solana validators ship upgrade"]
    assert sol.published_at == dt.datetime(2026, 10, 27, 13, 0, tzinfo=UTC)  # -0400 -> UTC
    assert by_title["Solar power and soldiers: a macro story"].coins == ()
    assert by_title["Posted from the future: $ETH ETF flows"].published_at == NOW
    assert all(i.source == "Example" for i in items)


def test_dedupe_keeps_earliest_per_url_and_title() -> None:
    content = (FIXTURES / "rss_sample.xml").read_bytes()
    items = news.parse_feed(content, "Example", news.alias_patterns(ALIASES), NOW)
    kept = news.dedupe(items + items)
    assert len(kept) == 4
    tops = [i for i in kept if "100k" in i.title.casefold()]
    assert [i.url for i in tops] == ["https://news.example.com/markets/btc-100k?id=7"]


@respx.mock
def test_fetch_all_reports_failed_feeds_and_keeps_others() -> None:
    respx.get("https://a.example/rss").mock(
        return_value=httpx.Response(200, content=(FIXTURES / "rss_sample.xml").read_bytes())
    )
    respx.get("https://b.example/rss").mock(return_value=httpx.Response(503))
    feeds = [news.Feed("A", "https://a.example/rss"), news.Feed("B", "https://b.example/rss")]
    with httpx.Client() as client:
        items, failed = news.fetch_all(client, feeds, news.alias_patterns(ALIASES), NOW)
    assert failed == ["B"] and len(items) == 4


def test_repo_feeds_config() -> None:
    names = [f.name for f in news.load_feeds()]
    assert names == ["CoinDesk", "Cointelegraph", "Decrypt", "The Block"]


# --- Calendar ---------------------------------------------------------------------------------


def test_repo_calendar_yaml_is_valid_and_covers_the_range() -> None:
    events = cal.load_yaml()
    fomc = [e for e in events if e["kind"] == "fomc"]
    cpi = [e for e in events if e["kind"] == "cpi"]
    assert len(fomc) == 10 and len(cpi) == 15  # 2026-10 .. 2027-12
    assert min(e["date"] for e in events) >= D(2026, 10, 1)
    assert max(e["date"] for e in events) <= D(2027, 12, 31)
    assert {e["date"].month for e in cpi if e["date"].year == 2027} == set(range(1, 13))
    # 2:00 pm ET and 8:30 am ET, in UTC (EDT or EST)
    assert {e["time_utc"] for e in fomc} <= {dt.time(18), dt.time(19)}
    assert {e["time_utc"] for e in cpi} <= {dt.time(12, 30), dt.time(13, 30)}
    assert all(e["source_url"].startswith("https://www.") for e in events)


def test_calendar_yaml_rejects_unknown_kinds_and_duplicates(tmp_path) -> None:
    path = tmp_path / "calendar.yaml"
    path.write_text("events:\n  - {date: 2026-11-01, kind: gdp, title: GDP}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown calendar kind"):
        cal.load_yaml(path)
    path.write_text(
        "events:\n  - {date: 2026-11-01, kind: cpi, title: CPI}\n"
        "  - {date: 2026-11-01, kind: cpi, title: CPI}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        cal.load_yaml(path)


# --- live (RUN_LIVE=1) ------------------------------------------------------------------------


def _today() -> D:
    return dt.datetime.now(UTC).date()


@pytest.mark.live
def test_live_fng_recent_days() -> None:
    with http.make_client() as client:
        points = sentiment.fetch(client, limit=5)
    assert len(points) == 5 and points[-1][0] >= _today() - dt.timedelta(days=2)


@pytest.mark.live
def test_live_coinmetrics_onchain_metrics() -> None:
    start = _today() - dt.timedelta(days=7)
    with coinmetrics.make_client() as client:
        out = coinmetrics.fetch_asset_metrics(client, "btc", coinmetrics.METRICS, start)
    assert all(len(points) >= 5 for points in out.values())


@pytest.mark.live
def test_live_fred_observations() -> None:
    key = get_settings().fred_api_key
    if key is None:
        pytest.skip("FRED_API_KEY not set")
    with fred.make_client() as client:
        points = fred.fetch_observations(
            client, "DGS10", key.get_secret_value(), _today() - dt.timedelta(days=30)
        )
    assert len(points) >= 15


@pytest.mark.live
def test_live_coingecko_dominance() -> None:
    key = get_settings().coingecko_demo_key
    if key is None:
        pytest.skip("COINGECKO_DEMO_KEY not set")
    with dominance.make_client(key.get_secret_value()) as client:
        resp = client.get("/global")
        resp.raise_for_status()
    day, values = dominance.parse_global(resp.json())
    assert day >= _today() - dt.timedelta(days=1) and 30 < values["btc"] < 90


@pytest.mark.live
def test_live_rss_feeds() -> None:
    with http.make_client() as client:
        items, failed = news.fetch_all(
            client, news.load_feeds(), news.alias_patterns(ALIASES), dt.datetime.now(UTC)
        )
    assert failed == [] and len(items) >= 20
