"""`/api/views` and `/api/admin/views` (Stage 6.2): MCO extracts and manual views merged newest
first, the as-of rule, MCO switched off, admin-only writes and validation, and the desk-mcp
tool that wraps the same function. Uses the seeded fake MCO video in `api_fakes`."""

import datetime as dt
import json

from desk.api.routes import views
from desk.mcp_server import tools
from tests.api_fakes import ADMIN, MCO_VIDEO, MEMBER, PENDING_CANARY, auth

VIEW = {
    "source": "Some Analyst",
    "coin": "btc",
    "bias": "bullish",
    "levels": [{"price": 70000, "label": "breakout"}],
    "invalidation": 61000,
    "url": "https://example.com/post",
}


def add(api, body=None):
    return api.post("/api/admin/views", json=body or VIEW, headers=auth(ADMIN))


def test_mco_view_from_the_extract(api) -> None:
    r = api.get("/api/views?coin=BTC", headers=auth(MEMBER))
    assert r.status_code == 200
    (v,) = r.json()["data"]
    assert v["id"] == f"mco:{MCO_VIDEO}" and v["kind"] == "mco"
    assert v["source"] == "More Crypto Online" and v["bias"] == "bearish"
    assert v["targets"] == [58000.0] and v["invalidation"] == 70000.0
    assert [s["name"] for s in v["scenarios"]] == ["primary", "alternative"]
    assert PENDING_CANARY not in r.text  # stored v1 labels never come out
    assert api.get("/api/views?coin=SOL", headers=auth(MEMBER)).json()["data"] == []


def test_manual_views_merge_newest_first_and_delete(api) -> None:
    r = add(api)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["kind"] == "manual" and created["coin"] == "BTC"
    assert created["levels"] == [{"price": 70000.0, "label": "breakout"}]
    data = api.get("/api/views?coin=BTC", headers=auth(MEMBER)).json()
    assert [v["kind"] for v in data["data"]] == ["manual", "mco"]
    assert {s["name"] for s in data["sources"]} == {"Some Analyst", "More Crypto Online"}
    row_id = int(created["id"].split(":")[1])
    assert api.delete(f"/api/admin/views/{row_id}", headers=auth(ADMIN)).status_code == 204
    assert api.delete(f"/api/admin/views/{row_id}", headers=auth(ADMIN)).status_code == 404
    assert [v["kind"] for v in api.get("/api/views", headers=auth(MEMBER)).json()["data"]] == [
        "mco"
    ]


def test_as_of_rule(api) -> None:
    add(api)  # created now, so not visible as of an earlier day
    before = api.get("/api/views?as_of=2026-10-25", headers=auth(MEMBER)).json()
    assert before["data"] == [] and before["as_of"] == "2026-10-25"
    on_day = api.get("/api/views?as_of=2026-10-26", headers=auth(MEMBER)).json()["data"]
    assert [v["kind"] for v in on_day] == ["mco"]  # published 13:00 UTC on the day


def test_mco_switched_off_leaves_manual_views(api, monkeypatch) -> None:
    from desk.jobs import mco_daily

    add(api)
    monkeypatch.setattr(mco_daily, "enabled", lambda: False)
    data = api.get("/api/views", headers=auth(MEMBER)).json()["data"]
    assert [v["kind"] for v in data] == ["manual"]
    cards = api.get("/api/overview", headers=auth(MEMBER)).json()["data"]["coins"]
    assert cards[0]["mco_bias"] is None


def test_writes_are_admin_only_and_validated(api) -> None:
    assert api.post("/api/admin/views", json=VIEW, headers=auth(MEMBER)).status_code == 403
    bad = [
        {**VIEW, "source": "  "},
        {**VIEW, "bias": "moon"},
        {**VIEW, "url": "javascript:alert(1)"},
        {**VIEW, "levels": [{"price": -1, "label": "x"}]},
        {**VIEW, "coin": "NOPE"},
    ]
    for body in bad:
        assert add(api, body).status_code in (404, 422), body
    assert api.delete(f"/api/admin/views/{1}", headers=auth(MEMBER)).status_code == 403


def test_desk_mcp_tool_wraps_the_same_function(api, api_sessions, monkeypatch) -> None:
    add(api)
    token = tools.session_override.set(api_sessions)
    try:
        body = json.loads(tools.get_external_views("BTC"))
        cut = json.loads(tools.get_external_views("BTC", as_of="2026-10-26"))
    finally:
        tools.session_override.reset(token)
    kinds = [v["kind"] for v in body["data"]["views"]]
    assert kinds == ["manual", "mco"] and "untrusted" in body["data"]
    assert [v["kind"] for v in cut["data"]["views"]] == ["mco"] and cut["as_of"] == "2026-10-26"
    with api_sessions() as s:
        direct = views.list_views(s, dt.date(2026, 10, 26), "BTC")
    assert [v.kind for v in direct.data] == ["mco"]
