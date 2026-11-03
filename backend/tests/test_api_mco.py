"""`/api/mco` (Stage 6.1): members see only approved/edited labels and never the raw
pivot_labels; the review list is admin-only; everything is 404 when MCO is off; the MCO tables
stay out of members' Data tab (Decision 6). Uses the seeded fake video in `api_fakes`."""

from desk.api.routes import mco
from tests.api_fakes import ADMIN, MCO_VIDEO, MEMBER, PENDING_CANARY, auth


def test_members_see_only_approved_labels_and_no_raw_pivot_labels(api) -> None:
    r = api.get("/api/mco/videos", headers=auth(MEMBER))
    assert r.status_code == 200
    body = r.json()
    assert [v["video_id"] for v in body["data"]] == [MCO_VIDEO]  # status `new` is not listed
    video = body["data"][0]
    assert [lab["label"] for lab in video["labels"]] == ["1"]
    assert video["coins"][0]["bias"] == "bearish" and "pivot_labels" not in video["coins"][0]
    assert PENDING_CANARY not in r.text and "PENDING" not in r.text
    assert body["sources"][0]["name"] == "More Crypto Online (YouTube)"
    one = api.get(f"/api/mco/videos/{MCO_VIDEO}", headers=auth(MEMBER))
    assert [lab["status"] for lab in one.json()["data"]["labels"]] == ["approved"]
    assert PENDING_CANARY not in one.text
    assert api.get("/api/mco/videos/fakeVideo02", headers=auth(MEMBER)).status_code == 404


def test_coin_filter(api) -> None:
    assert len(api.get("/api/mco/videos?coin=btc", headers=auth(MEMBER)).json()["data"]) == 1
    assert api.get("/api/mco/videos?coin=SOL", headers=auth(MEMBER)).json()["data"] == []


def test_review_is_admin_only_and_lists_pending(api) -> None:
    assert api.get("/api/admin/mco/review", headers=auth(MEMBER)).status_code == 403
    r = api.get("/api/admin/mco/review", headers=auth(ADMIN))
    labels = r.json()["data"][0]["labels"]
    assert [(lab["label"], lab["status"]) for lab in labels] == [("PENDING", "pending")]
    assert "match_note" in labels[0]


def test_everything_404_when_mco_is_off(api, monkeypatch) -> None:
    from desk.jobs import mco_daily

    monkeypatch.setattr(mco_daily, "enabled", lambda: False)
    for path in ("/api/mco/videos", f"/api/mco/videos/{MCO_VIDEO}", "/api/admin/mco/review"):
        assert api.get(path, headers=auth(ADMIN)).status_code == 404, path
    assert api.get("/api/mco/videos").status_code == 401  # login first, then the flag
    assert mco.mco_on is not None


def test_mco_tables_are_not_in_members_data_tab(api) -> None:
    names = {t["name"] for t in api.get("/api/data/tables", headers=auth(MEMBER)).json()["data"]}
    assert not names & {"mco_videos", "mco_extracts", "mco_wave_labels", "external_views"}
    for table in ("mco_videos", "mco_extracts", "mco_wave_labels"):
        r = api.get(f"/api/data/tables/{table}/export.csv", headers=auth(MEMBER))
        assert r.status_code in (403, 404), table
