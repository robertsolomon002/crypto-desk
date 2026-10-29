"""The Data tab: visibility per role, own rows, filters, paging, CSV export (Stage 2.1)."""

import csv
import io

import pytest
from sqlalchemy import select

from desk.api.routes.data import csv_cell
from desk.models import AgentSnapshot, User
from tests.api_fakes import ADMIN, MEMBER, OTHER_MEMBER, auth


def tables(api, who: str) -> set[str]:
    return {t["name"] for t in api.get("/api/data/tables", headers=auth(who)).json()["data"]}


def test_visibility_per_role(api) -> None:
    member, admin = tables(api, MEMBER), tables(api, ADMIN)
    assert {"candles_daily", "series", "news", "signals", "agent_snapshots"} <= member
    hidden = {"users", "job_runs", "llm_spend", "analytics_cache", "mco_videos", "mco_extracts",
              "mco_wave_labels", "external_views"}  # fmt: skip
    assert not member & hidden
    assert hidden <= admin
    for name in hidden:
        assert api.get(f"/api/data/tables/{name}", headers=auth(MEMBER)).status_code == 404
        r = api.get(f"/api/data/tables/{name}/export.csv", headers=auth(MEMBER))
        assert r.status_code == 404
    assert api.get("/api/data/tables/pg_user", headers=auth(ADMIN)).status_code == 404


def test_mco_tables_hidden_when_mco_is_off(api, monkeypatch) -> None:
    from desk.config import get_settings

    monkeypatch.setenv("MCO_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert not {t for t in tables(api, ADMIN) if t.startswith("mco_")}
    finally:
        get_settings.cache_clear()


def test_own_rows_only(api, api_sessions) -> None:
    for who in (MEMBER, OTHER_MEMBER):
        api.get("/api/me", headers=auth(who))  # creates the users
    with api_sessions.begin() as s:
        ids = dict(s.execute(select(User.clerk_id, User.id)).all())
        for owner in (MEMBER, OTHER_MEMBER, OTHER_MEMBER):
            s.add(AgentSnapshot(user_id=ids[owner], tool="t", args={}, result={}))

    def rows(who: str) -> list[dict]:
        r = api.get("/api/data/tables/agent_snapshots", headers=auth(who))
        return r.json()["data"]["rows"]

    assert {r["user_id"] for r in rows(MEMBER)} == {ids[MEMBER]}
    assert len(rows(OTHER_MEMBER)) == 2
    assert len(rows(ADMIN)) == 3
    # A filter cannot widen the owner restriction.
    url = f"/api/data/tables/agent_snapshots?filter=user_id:eq:{ids[OTHER_MEMBER]}"
    assert api.get(url, headers=auth(MEMBER)).json()["data"]["rows"] == []
    counts = {t["name"]: t["rows"] for t in
              api.get("/api/data/tables", headers=auth(MEMBER)).json()["data"]}  # fmt: skip
    assert counts["agent_snapshots"] == 1
    export = api.get("/api/data/tables/agent_snapshots/export.csv", headers=auth(MEMBER))
    csv_rows = list(csv.reader(io.StringIO(export.text)))
    assert len(csv_rows) == 2  # header + own row


def test_filters_order_and_paging(api) -> None:
    h = auth(MEMBER)
    base = "/api/data/tables/candles_daily"
    q = f"{base}?filter=coin:eq:ETH&filter=date:gte:2026-10-01&order=date&desc=false&page_size=10"
    page1 = api.get(q, headers=h).json()["data"]
    assert page1["total"] == 27
    assert [r["date"] for r in page1["rows"]][:2] == ["2026-10-01", "2026-10-02"]
    page3 = api.get(q + "&page=3", headers=h).json()["data"]
    assert len(page3["rows"]) == 7
    news = api.get("/api/data/tables/news?filter=coins:contains:ETH", headers=h).json()["data"]
    assert [r["title"] for r in news["rows"]] == ["Ether upgrade lands"]
    like = api.get("/api/data/tables/news?filter=title:contains:100%25", headers=h).json()
    assert like["data"]["total"] == 0  # % is escaped, not a wildcard


@pytest.mark.parametrize(
    "query",
    [
        "filter=nope:eq:1",
        "filter=close:between:1",
        "filter=close:eq:abc",
        "filter=date:gte:yesterday",
        "filter=coins:eq:BTC",
        "order=nope",
        "page_size=501",
        "filter=close:eq:1;DROP TABLE coins",
    ],
)
def test_bad_queries(api, query) -> None:
    r = api.get(f"/api/data/tables/candles_daily?{query}", headers=auth(MEMBER))
    assert r.status_code in (400, 422)


def test_csv_export(api) -> None:
    r = api.get("/api/data/tables/news/export.csv?order=published_at&desc=false",
                headers=auth(MEMBER))  # fmt: skip
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="news_' in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 3
    assert rows[0]["title"].startswith("'=HYPERLINK")  # neutralized formula


def test_csv_cell() -> None:
    assert csv_cell("=1+1") == "'=1+1"
    assert csv_cell("@SUM(A1)") == "'@SUM(A1)"
    assert csv_cell("-5 cmd") == "'-5 cmd"
    assert csv_cell("plain") == "plain"
    assert csv_cell(-5.0) == -5.0  # numbers stay numbers
    assert csv_cell(["=x"]) == "['=x']"
