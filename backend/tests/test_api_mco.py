"""`/api/mco` (Stages 6.1 and D49): scenarios per coin, no wave labels for anyone (neither
label rows nor raw labels in stored v1 payloads), 404 when MCO is off, and the MCO tables out of
members' Data tab (Decision 6). Uses the seeded fake v1 video in `api_fakes`."""

from tests.api_fakes import ADMIN, MCO_VIDEO, MEMBER, PENDING_CANARY, auth


def test_videos_come_as_scenarios_without_any_labels(api) -> None:
    for who in (MEMBER, ADMIN):
        r = api.get("/api/mco/videos", headers=auth(who))
        assert r.status_code == 200
        body = r.json()
        assert [v["video_id"] for v in body["data"]] == [MCO_VIDEO]  # status `new` is not listed
        video = body["data"][0]
        assert "labels" not in video and video["prompt_version"] == "mco_extract_v1"
        coin = video["coins"][0]
        assert coin["bias"] == "bearish" and "pivot_labels" not in coin
        assert [(s["name"], s["targets"]) for s in coin["scenarios"]] == [
            ("primary", [58000.0]),
            ("alternative", []),
        ]
        assert PENDING_CANARY not in r.text and "wave_label" not in r.text
        assert body["sources"][0]["name"] == "More Crypto Online (YouTube)"
    one = api.get(f"/api/mco/videos/{MCO_VIDEO}", headers=auth(MEMBER))
    assert one.json()["data"]["coins"][0]["scenarios"][0]["invalidation"] == 70000.0
    assert PENDING_CANARY not in one.text
    assert api.get("/api/mco/videos/fakeVideo02", headers=auth(MEMBER)).status_code == 404


def test_coin_filter(api) -> None:
    assert len(api.get("/api/mco/videos?coin=btc", headers=auth(MEMBER)).json()["data"]) == 1
    assert api.get("/api/mco/videos?coin=SOL", headers=auth(MEMBER)).json()["data"] == []


def test_review_route_is_gone(api) -> None:
    assert api.get("/api/admin/mco/review", headers=auth(ADMIN)).status_code == 404


def test_everything_404_when_mco_is_off(api, monkeypatch) -> None:
    from desk.jobs import mco_daily

    monkeypatch.setattr(mco_daily, "enabled", lambda: False)
    for path in ("/api/mco/videos", f"/api/mco/videos/{MCO_VIDEO}"):
        assert api.get(path, headers=auth(ADMIN)).status_code == 404, path
    assert api.get("/api/mco/videos").status_code == 401  # login first, then the flag


def test_mco_tables_are_not_in_members_data_tab(api) -> None:
    names = {t["name"] for t in api.get("/api/data/tables", headers=auth(MEMBER)).json()["data"]}
    assert not names & {"mco_videos", "mco_extracts", "mco_wave_labels", "external_views"}
    for table in ("mco_videos", "mco_extracts", "mco_wave_labels"):
        r = api.get(f"/api/data/tables/{table}/export.csv", headers=auth(MEMBER))
        assert r.status_code in (403, 404), table
