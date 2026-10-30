"""Every read route against a seeded Postgres, and the role matrix over every route (Stage 2.1).

`SAMPLES` must name every `/api` route: a new route fails `test_every_route_has_a_sample` until
it is added here, so it cannot skip the role checks.
"""

import datetime as dt
from types import SimpleNamespace

import httpx
import pytest
import respx

from desk.api.main import app
from desk.api.routes import admin
from tests.api_fakes import ADMIN, LAST_DAY, MEMBER, auth

CLERK = "https://api.clerk.com/v1"
INVITE = {"id": "inv_1", "email_address": "friend@example.com", "status": "pending",
          "created_at": 1761696000000}  # fmt: skip

# (method, path template) -> (url, json body)
SAMPLES: dict[tuple[str, str], tuple[str, dict | None]] = {
    ("GET", "/api/me"): ("/api/me", None),
    ("GET", "/api/coins"): ("/api/coins", None),
    ("GET", "/api/overview"): ("/api/overview", None),
    ("GET", "/api/ohlcv/{coin}"): ("/api/ohlcv/BTC", None),
    ("GET", "/api/indicators/{coin}"): ("/api/indicators/BTC?sma=20", None),
    ("GET", "/api/levels/{coin}"): ("/api/levels/BTC", None),
    ("GET", "/api/pivots/{coin}"): ("/api/pivots/BTC", None),
    ("GET", "/api/regime/{coin}"): ("/api/regime/BTC", None),
    ("GET", "/api/cycles/{coin}/anchors"): ("/api/cycles/BTC/anchors", None),
    ("GET", "/api/cycles/{coin}/paths"): ("/api/cycles/BTC/paths", None),
    ("GET", "/api/cycles/{coin}/day-n"): ("/api/cycles/BTC/day-n", None),
    ("GET", "/api/cycles/{coin}/roi"): ("/api/cycles/BTC/roi", None),
    ("GET", "/api/cycles/{coin}/yoy"): ("/api/cycles/BTC/yoy", None),
    ("GET", "/api/stats/{coin}/seasonality/{period}"): ("/api/stats/ETH/seasonality/monthly", None),
    ("GET", "/api/stats/{coin}/distribution"): ("/api/stats/ETH/distribution", None),
    ("GET", "/api/stats/{coin}/drawdowns"): ("/api/stats/ETH/drawdowns", None),
    ("GET", "/api/stats/{coin}/drawdown-episodes"): ("/api/stats/ETH/drawdown-episodes", None),
    ("GET", "/api/stats/{coin}/volatility"): ("/api/stats/ETH/volatility", None),
    ("GET", "/api/stats/{coin}/correlation"): ("/api/stats/ETH/correlation", None),
    ("GET", "/api/onchain/{coin}"): ("/api/onchain/BTC", None),
    ("GET", "/api/macro"): ("/api/macro", None),
    ("GET", "/api/macro/fng"): ("/api/macro/fng", None),
    ("GET", "/api/macro/dominance"): ("/api/macro/dominance", None),
    ("GET", "/api/news"): ("/api/news", None),
    ("GET", "/api/calendar"): ("/api/calendar?as_of=2026-10-27", None),
    ("GET", "/api/data/tables"): ("/api/data/tables", None),
    ("GET", "/api/data/tables/{name}"): ("/api/data/tables/coins", None),
    ("GET", "/api/data/tables/{name}/export.csv"): ("/api/data/tables/coins/export.csv", None),
    ("GET", "/api/admin/watchlist"): ("/api/admin/watchlist", None),
    ("POST", "/api/admin/watchlist"): ("/api/admin/watchlist", {"symbol": "LINK", "name": "Link"}),
    ("DELETE", "/api/admin/watchlist/{symbol}"): ("/api/admin/watchlist/LINK", None),
    ("GET", "/api/admin/invites"): ("/api/admin/invites", None),
    ("POST", "/api/admin/invites"): ("/api/admin/invites", {"email": "friend@example.com"}),
    ("DELETE", "/api/admin/invites/{invite_id}"): ("/api/admin/invites/inv_1", None),
    ("GET", "/api/admin/users"): ("/api/admin/users", None),
    ("PATCH", "/api/admin/users/{user_id}"): ("/api/admin/users/1", {"role": "admin"}),
}  # fmt: skip
PUBLIC = {("GET", "/api/health")}


def api_routes() -> list[tuple[str, str]]:
    """Every operation in the OpenAPI schema (FastAPI 0.162 nests included routers, so the
    schema is the reliable list, and it is the contract anyway)."""
    return sorted(
        (method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops
    )


@pytest.fixture
def clerk(api):
    """Clerk's Backend API, mocked; the admin routes get a client without a real secret."""

    def client():
        with httpx.Client(base_url=CLERK) as c:
            yield c

    app.dependency_overrides[admin.clerk_client] = client
    with respx.mock(base_url=CLERK, assert_all_called=False) as mock:
        mock.get("/invitations").respond(json=[INVITE])
        mock.post("/invitations").respond(json=INVITE)
        mock.post("/invitations/inv_1/revoke").respond(json={**INVITE, "status": "revoked"})
        yield mock


def test_every_route_has_a_sample() -> None:
    assert set(api_routes()) == set(SAMPLES) | PUBLIC


@pytest.mark.parametrize("route", sorted(SAMPLES))
def test_anonymous_gets_401(api, route) -> None:
    url, body = SAMPLES[route]
    assert api.request(route[0], url, json=body).status_code == 401


def test_roles_on_every_route(api, clerk) -> None:
    """Members: 403 on admin routes, success elsewhere. Admins: success everywhere."""
    for (method, path), (url, body) in SAMPLES.items():
        r = api.request(method, url, json=body, headers=auth(MEMBER))
        if path.startswith("/api/admin"):
            assert r.status_code == 403, (method, path)
        else:
            assert r.is_success, (method, path, r.status_code, r.text[:300])
    for (method, path), (url, body) in SAMPLES.items():  # dict order: POST before DELETE
        r = api.request(method, url, json=body, headers=auth(ADMIN))
        assert r.is_success, (method, path, r.status_code, r.text[:300])


# --- Envelope and as_of on the read routes ----------------------------------------------------

READS = [url for (m, p), (url, _) in SAMPLES.items()
         if m == "GET" and not p.startswith(("/api/admin", "/api/me", "/api/data"))]  # fmt: skip


@pytest.mark.parametrize("url", READS)
def test_envelope_has_provenance(api, url) -> None:
    body = api.get(url, headers=auth(MEMBER)).json()
    assert set(body) == {"as_of", "sources", "data"}
    assert body["sources"] and all(s["name"] for s in body["sources"])
    today = dt.datetime.now(dt.UTC).date()
    assert body["as_of"] is None or dt.date.fromisoformat(body["as_of"]) <= today


def test_as_of_truncates(api) -> None:
    h = auth(MEMBER)
    full = api.get("/api/ohlcv/BTC", headers=h).json()
    cut = api.get("/api/ohlcv/BTC?as_of=2025-06-30", headers=h).json()
    assert full["as_of"] == LAST_DAY.isoformat()
    assert cut["as_of"] == "2025-06-30"
    assert cut["data"][-1]["time"].startswith("2025-06-30")
    ind = api.get("/api/indicators/BTC?sma=50&as_of=2025-06-30", headers=h).json()
    assert ind["data"]["result"][-1]["date"] == "2025-06-30"
    assert api.get("/api/levels/BTC?as_of=2025-06-30", headers=h).json()["as_of"] == "2025-06-30"
    news = api.get("/api/news?as_of=2026-10-27", headers=h).json()["data"]
    assert [n["title"] for n in news] == ["Ether upgrade lands",
                                          '=HYPERLINK("http://evil") Bitcoin rallies']  # fmt: skip
    future = (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=2)).isoformat()
    assert api.get(f"/api/ohlcv/BTC?as_of={future}", headers=h).status_code == 422


def test_indicators_selection_matches_full_set(api) -> None:
    """The selectable indicators equal the fixed-set `indicators` registry function."""
    h = auth(MEMBER)
    url = "/api/indicators/BTC?sma=20,50&ema=200&bb=20:2&rsi=14&macd=12:26:9&vol=30&band=true"
    got = api.get(url, headers=h).json()["data"]["result"][-1]
    from desk.analytics import registry
    from desk.analytics.inputs import load_inputs
    from desk.api import deps

    with deps.open_session() as s:
        ref = registry.run_json("indicators", load_inputs(s, ["BTC"]), "BTC")[-1]
    pairs = {"sma20": "sma20", "sma50": "sma50", "ema200": "ema200", "bb20_2_upper": "bb_upper",
             "rsi14": "rsi14", "macd12_26_9_hist": "macd_hist", "vol30": "vol30",
             "sma20w": "sma20w"}  # fmt: skip
    for mine, theirs in pairs.items():
        assert got[mine] == pytest.approx(ref[theirs]), mine


@pytest.mark.parametrize(
    "query", ["sma=1", "sma=abc", "bb=20", "macd=26:12:9", "rsi=1", "sma=1,2,3,4,5,6,7"]
)
def test_indicator_params_are_validated(api, query) -> None:
    assert api.get(f"/api/indicators/BTC?{query}", headers=auth(MEMBER)).status_code == 422


def test_weekly_and_4h(api) -> None:
    h = auth(MEMBER)
    weeks = api.get("/api/ohlcv/ETH?tf=1w", headers=h).json()["data"]
    assert all(dt.datetime.fromisoformat(w["time"]).weekday() == 0 for w in weeks)
    assert api.get("/api/ohlcv/ETH?tf=4h", headers=h).json()["data"] == []  # filled from 3.2


def test_unknown_coin_and_unsupported(api) -> None:
    h = auth(MEMBER)
    assert api.get("/api/ohlcv/DOGE", headers=h).status_code == 404
    assert api.get("/api/onchain/SOL", headers=h).status_code == 404  # no Coin Metrics data
    assert api.get("/api/cycles/SOL/anchors", headers=h).status_code == 404


def test_heavy_routes_use_the_cache(api) -> None:
    h = auth(MEMBER)
    first = api.get("/api/stats/ETH/seasonality/monthly", headers=h).json()["data"]
    second = api.get("/api/stats/ETH/seasonality/monthly", headers=h).json()["data"]
    assert (first["cached"], second["cached"]) == (False, True)
    assert first["result"] == second["result"]


def test_macro_applies_release_lags(api) -> None:
    rows = api.get("/api/macro?as_of=2026-10-01", headers=auth(MEMBER)).json()["data"]["rows"]
    m2 = [r for r in rows if r["M2SL"] is not None]
    assert m2[-1]["date"] == "2026-08-01"  # Sep 1 + 60 days is after Oct 1


def test_coins_and_calendar(api) -> None:
    h = auth(MEMBER)
    coins = api.get("/api/coins", headers=h).json()["data"]
    assert [c["symbol"] for c in coins] == ["BTC", "ETH", "SOL"]
    assert coins[0]["last_date"] == LAST_DAY.isoformat()
    events = api.get("/api/calendar?as_of=2026-10-27&days_ahead=30&kind=cpi", headers=h).json()
    assert [e["kind"] for e in events["data"]] == ["cpi"]


def test_etag_and_gzip(api) -> None:
    h = auth(MEMBER)
    r = api.get("/api/ohlcv/BTC", headers={**h, "Accept-Encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip"
    etag = r.headers["etag"]
    assert etag.startswith('W/"')
    assert r.headers["cache-control"] == "private, no-cache"
    again = api.get("/api/ohlcv/BTC", headers={**h, "If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert api.get("/api/ohlcv/BTC", headers={**h, "If-None-Match": 'W/"x"'}).status_code == 200


def test_overview_cards_and_freshness(api, api_sessions) -> None:
    from desk.analytics import registry
    from desk.analytics.inputs import load_inputs
    from desk.models import JobRun

    h = auth(MEMBER)
    with api_sessions() as s:
        s.add(JobRun(job="daily", status="failed", error="secret stack trace",
                     started_at=dt.datetime(2026, 10, 28, 0, 20, tzinfo=dt.UTC)))  # fmt: skip
        s.commit()
        ref = registry.run_json("summary", load_inputs(s, ["BTC"]), "BTC")
    body = api.get("/api/overview", headers=h).json()
    assert body["as_of"] == LAST_DAY.isoformat()
    cards = body["data"]["coins"]
    assert [c["symbol"] for c in cards] == ["BTC", "ETH", "SOL"]
    btc = cards[0]
    for key in ("close", "change_1d", "change_7d", "change_30d", "ath", "ath_distance"):
        assert btc[key] == pytest.approx(ref[key]), key
    assert btc["regime"] == ref["regime"] and btc["signal"] is None and btc["mco_bias"] is None
    assert btc["ath_distance"] <= 0
    fresh = {f["source"]: f for f in body["data"]["freshness"]}
    assert fresh["Prices"]["last_date"] == LAST_DAY.isoformat()
    assert fresh["Headlines"]["last_date"] == "2026-10-28"
    assert fresh["FRED macro"]["max_age_days"] == 62
    job = body["data"]["daily_job"]
    assert job["status"] == "failed" and "error" not in job  # error text stays admin-only

    cut = api.get("/api/overview?as_of=2026-10-01", headers=h).json()
    assert cut["as_of"] == "2026-10-01" and cut["data"]["daily_job"] is None
    cut_fresh = {f["source"]: f for f in cut["data"]["freshness"]}
    assert cut_fresh["Headlines"]["last_date"] is None and cut_fresh["Headlines"]["stale"]
    assert cut_fresh["Prices"]["stale"] is False
    assert cut["data"]["coins"][0]["date"] == "2026-10-01"


def test_me_reports_features(api, monkeypatch) -> None:
    from desk.api.routes import coins

    flags = {"features": {"mco": True, "mco_tab": True, "agent": False, "signals": False,
                          "onchain_macro": True}}  # fmt: skip
    monkeypatch.setattr(coins, "load_app_settings", lambda: flags)
    me = api.get("/api/me", headers=auth(MEMBER)).json()
    assert me["role"] == "member"
    assert me["features"] == {"onchain_macro": True, "mco": True, "agent": False,
                              "signals": False}  # fmt: skip
    monkeypatch.setattr(coins, "get_settings", lambda: SimpleNamespace(mco_enabled=False))
    assert api.get("/api/me", headers=auth(MEMBER)).json()["features"]["mco"] is False
