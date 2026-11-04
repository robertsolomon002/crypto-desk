"""`/api/signals` (Stage 7.2, D52): weeks, a week with its brief, history, the scorecard and
the desk debate; MCO-derived rows on screen for members, out of their CSV exports, and out of
everything when MCO is off; the Overview's latest desk signal."""

import csv
import io

import pytest

from tests.api_fakes import ADMIN, BRIEF_CANARY, MEMBER, OPEN_WEEK, SIGNAL_WEEK, auth

H = auth(MEMBER)


@pytest.fixture
def mco_off(monkeypatch):
    from desk.jobs import mco_daily

    monkeypatch.setattr(mco_daily, "enabled", lambda: False)


def test_no_signals_yet(api) -> None:
    assert api.get("/api/signals/week", headers=H).status_code == 404
    weeks = api.get("/api/signals/weeks", headers=H).json()
    assert weeks["data"]["weeks"] == [] and weeks["as_of"] is None
    card = api.get("/api/signals/scorecard", headers=H).json()["data"]
    assert card["sources"] == [] and card["early_weeks"] == 12


def test_weeks_and_the_latest_week(api, signals_data) -> None:
    weeks = api.get("/api/signals/weeks", headers=H).json()
    assert weeks["data"]["versions"] == [1]
    assert [(w["week"], w["signals"], w["resolved"], w["has_brief"])
            for w in weeks["data"]["weeks"]] == [
        (OPEN_WEEK.isoformat(), 2, 0, False), (SIGNAL_WEEK.isoformat(), 5, 5, True),
    ]  # fmt: skip
    latest = api.get("/api/signals/week", headers=H).json()
    assert latest["as_of"] == "2026-10-25"
    week = latest["data"]
    assert week["week"] == OPEN_WEEK.isoformat() and week["resolves_on"] == "2026-11-03"
    assert week["brief"] is None and week["withheld"] is None
    assert [(s["coin"], s["source"], s["outcome"]) for s in week["signals"]] == [
        ("BTC", "desk", None), ("BTC", "coinflip", None),
    ]  # fmt: skip
    assert week["signals"][0]["has_debate"] is False  # no run saved


def test_a_resolved_week_with_its_brief(api, signals_data) -> None:
    week = api.get(f"/api/signals/week?week={SIGNAL_WEEK}", headers=H).json()["data"]
    assert [(s["coin"], s["source"]) for s in week["signals"]] == [
        ("BTC", "desk"), ("BTC", "coinflip"), ("BTC", "trend"), ("BTC", "mco"),
        ("ETH", "coinflip"),
    ]  # fmt: skip
    desk = week["signals"][0]
    assert desk["has_debate"] and desk["outcome"]["first_hit"] == "neither"
    assert desk["outcome"]["week_close"] == 105.0 and len(desk["hash"]) == 64
    brief = week["brief"]
    assert len(brief["summary"]) == 5 and brief["coins"][0]["levels_to_watch"][0]["price"] == 90
    assert BRIEF_CANARY in brief["content"]
    assert api.get("/api/signals/week?week=2026-10-12", headers=H).status_code == 404


def test_history_filters(api, signals_data) -> None:
    rows = api.get("/api/signals/history", headers=H).json()["data"]
    assert len(rows) == 7 and rows[0]["week"] == OPEN_WEEK.isoformat()
    eth = api.get("/api/signals/history?coin=eth", headers=H).json()["data"]
    assert [(r["coin"], r["source"]) for r in eth] == [("ETH", "coinflip")]
    desk = api.get("/api/signals/history?source=desk", headers=H).json()["data"]
    assert [r["week"] for r in desk] == [OPEN_WEEK.isoformat(), SIGNAL_WEEK.isoformat()]
    assert api.get("/api/signals/history?source=nope", headers=H).status_code == 422


def test_scorecard(api, signals_data) -> None:
    body = api.get("/api/signals/scorecard", headers=H).json()
    card = body["data"]
    assert body["as_of"] == "2026-10-25"  # the end of the last resolved week
    assert card["paper_cost_per_side"] == 0.002
    assert [s["source"] for s in card["sources"]] == ["desk", "coinflip", "trend", "mco"]
    flip = card["sources"][1]
    assert flip["stats"]["signals"] == 2 and flip["stats"]["hit_rate"] == 0.5
    assert [c["coin"] for c in flip["coins"]] == ["BTC", "ETH"]
    desk = card["sources"][0]["stats"]
    assert desk["early_days"] and desk["target_first_rate"] == 0.0 and desk["with_levels"] == 1
    assert card["sources"][0]["cumulative"][0]["paper_return"] == pytest.approx(0.046)


def test_debate(api, signals_data) -> None:
    r = api.get(f"/api/signals/{signals_data['BTC:desk']}/debate", headers=H)
    assert r.status_code == 200
    run = r.json()["data"]
    assert run["signal"]["target"] == 110.0 and run["debate"]["bull_open"]["side"] == "bull"
    for name in ("BTC:coinflip", "open:BTC:desk"):
        assert api.get(f"/api/signals/{signals_data[name]}/debate", headers=H).status_code == 404
    assert api.get("/api/signals/999/debate", headers=H).status_code == 404


def test_mco_off_drops_mco_rows_and_keeps_back_that_weeks_brief(api, signals_data, mco_off):
    week = api.get(f"/api/signals/week?week={SIGNAL_WEEK}", headers=H).json()["data"]
    assert "mco" not in {s["source"] for s in week["signals"]}
    assert week["brief"] is None and "MCO" in week["withheld"]
    assert not any(s["has_debate"] for s in week["signals"])
    r = api.get(f"/api/signals/week?week={SIGNAL_WEEK}", headers=auth(ADMIN))
    assert BRIEF_CANARY not in r.text  # admins too
    debate = api.get(f"/api/signals/{signals_data['BTC:desk']}/debate", headers=H)
    assert debate.status_code == 404
    history = api.get("/api/signals/history", headers=H).json()["data"]
    assert "mco" not in {s["source"] for s in history}
    sources = api.get("/api/signals/scorecard", headers=H).json()["data"]["sources"]
    assert [s["source"] for s in sources] == ["desk", "coinflip", "trend"]
    weeks = api.get("/api/signals/weeks", headers=H).json()["data"]["weeks"]
    assert weeks[1]["signals"] == 4


def csv_rows(api, table: str, who: str) -> list[dict]:
    r = api.get(f"/api/data/tables/{table}/export.csv", headers=auth(who))
    assert r.status_code == 200
    return list(csv.DictReader(io.StringIO(r.text)))


def test_mco_rows_stay_out_of_member_exports(api, signals_data) -> None:
    mco_id = str(signals_data["BTC:mco"])
    browse = api.get("/api/data/tables/signals?page_size=50", headers=H).json()["data"]
    assert "mco" in {r["source"] for r in browse["rows"]}  # on screen: allowed
    assert "mco" not in {r["source"] for r in csv_rows(api, "signals", MEMBER)}
    assert mco_id not in {r["signal_id"] for r in csv_rows(api, "signal_outcomes", MEMBER)}
    assert csv_rows(api, "briefs", MEMBER) == []  # that week had MCO input
    assert "mco" in {r["source"] for r in csv_rows(api, "signals", ADMIN)}
    assert len(csv_rows(api, "briefs", ADMIN)) == 1


def test_mco_rows_hidden_from_everyone_when_mco_is_off(api, signals_data, mco_off) -> None:
    for who in (MEMBER, ADMIN):
        rows = api.get("/api/data/tables/signals?page_size=50", headers=auth(who)).json()
        assert "mco" not in {r["source"] for r in rows["data"]["rows"]}
        assert rows["data"]["total"] == 6
        briefs = api.get("/api/data/tables/briefs", headers=auth(who)).json()["data"]
        assert briefs["total"] == 0


def test_overview_shows_the_latest_desk_signal(api, signals_data) -> None:
    cards = {c["symbol"]: c for c in api.get("/api/overview", headers=H).json()["data"]["coins"]}
    assert cards["BTC"]["signal"] == {
        "id": signals_data["open:BTC:desk"], "week": OPEN_WEEK.isoformat(),
        "stance": "flat", "confidence": 0.55,
    }  # fmt: skip
    assert cards["ETH"]["signal"] is None  # coin-flip rows aren't the desk's
    before = api.get("/api/overview?as_of=2026-10-20", headers=H).json()["data"]["coins"]
    assert before[0]["signal"]["week"] == SIGNAL_WEEK.isoformat()
