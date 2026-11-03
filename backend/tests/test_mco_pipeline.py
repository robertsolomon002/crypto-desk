"""MCO discovery and the daily job against Postgres (Stage 6.1): RSS with the YouTube API
fallback, filters, dedupe, the daily cap, alerts, job_runs, and the privacy checks (no MCO text
in logs or the job summary, no writes under the repo). YouTube and Gemini are faked and every
title here is made up.

Needs TEST_DATABASE_URL (e.g. the docker-compose Postgres); skipped otherwise.
"""

import builtins
import datetime as dt
import io
import json
import logging
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select

from desk.agents import cost
from desk.config import REPO_ROOT
from desk.data import market
from desk.data.coins import seed_coins
from desk.jobs import mco_daily
from desk.mco import discover as disc
from desk.models import JobRun, LlmSpend, McoExtract, McoVideo, McoWaveLabel
from tests.test_mco_summarize import FakeGemini, good

NOW = dt.datetime(2026, 11, 4, 6, 30, tzinfo=dt.UTC)
CANARY = "MCO-TEXT-CANARY-91c4"
RSS = "https://www.youtube.com/feeds/videos.xml"
API = "https://www.googleapis.com/youtube/v3"


def entry(vid: str, title: str, hours_ago: float, desc: str = "") -> str:
    ts = (NOW - dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return (
        f"<entry><id>yt:video:{vid}</id><yt:videoId>{vid}</yt:videoId><title>{title}</title>"
        f"<published>{ts}</published><media:group><media:description>{desc}"
        f"</media:description></media:group></entry>"
    )


def feed(*entries: str) -> bytes:
    return (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
        'xmlns:media="http://search.yahoo.com/mrss/">' + "".join(entries) + "</feed>"
    ).encode()


VIDEOS = [  # id, title, hours ago, duration, live
    ("vidAAAAAAA1", f"Bitcoin wave count {CANARY}", 2, "PT12M3S", "none"),
    ("vidAAAAAAA2", "Ethereum update", 5, "PT9M", "none"),
    ("vidAAAAAAA3", "Crypto short", 6, "PT58S", "none"),
    ("vidAAAAAAA4", "Gold and silver", 7, "PT10M", "none"),
    ("vidAAAAAAA5", "Altcoins live", 1, "PT0S", "live"),
    ("vidAAAAAAA6", "Solana outlook", 30, "PT8M", "none"),
    ("vidAAAAAAA7", "Crypto market", 20, "PT1H2M", "none"),
    ("vidAAAAAAA8", "Old bitcoin video", 24 * 10, "PT10M", "none"),
]


def details_json() -> dict:
    return {
        "items": [
            {"id": v, "contentDetails": {"duration": d}, "snippet": {"liveBroadcastContent": live}}
            for v, _, _, d, live in VIDEOS
        ]
    }


def mock_youtube(mock: respx.MockRouter, rss_status: int = 200) -> None:
    if rss_status == 200:
        body = feed(*(entry(v, t, h, "solid desc") for v, t, h, _, _ in VIDEOS))
        mock.get(RSS).respond(200, content=body)
    else:
        mock.get(RSS).respond(rss_status)
    mock.get(f"{API}/channels").respond(
        json={"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUfake"}}}]}
    )
    mock.get(f"{API}/playlistItems").respond(
        json={
            "items": [
                {
                    "snippet": {
                        "title": t,
                        "description": "",
                        "publishedAt": "2026-01-01T00:00:00Z",
                    },
                    "contentDetails": {
                        "videoId": v,
                        "videoPublishedAt": (NOW - dt.timedelta(hours=h))
                        .isoformat()
                        .replace("+00:00", "Z"),
                    },
                }
                for v, t, h, _, _ in VIDEOS
            ]
        }
    )
    mock.get(f"{API}/videos").respond(json=details_json())


@pytest.fixture
def seeded(pg_sessions):
    with pg_sessions.begin() as s:
        seed_coins(s)
        start = dt.date(2026, 6, 1)
        rows = []
        for i in range(160):  # BTC zigzags: up 20 days, down 20 days around 60k
            day = start + dt.timedelta(days=i)
            px = 60000.0 * (1 + 0.12 * (1 - abs((i % 40) - 20) / 20))
            rows.append(
                {
                    "coin": "BTC",
                    "date": day,
                    "open": px,
                    "high": px * 1.005,
                    "low": px * 0.995,
                    "close": px,
                    "volume": 1.0,
                    "source": "coinbase",
                }
            )
        market.upsert_candles(s, rows)
    return pg_sessions


# --- Discovery --------------------------------------------------------------------------------


def test_discover_rss_filters_and_dedupes(seeded) -> None:
    with respx.mock(assert_all_called=False) as mock, httpx.Client() as http:
        mock_youtube(mock)
        with seeded() as s:
            r = disc.discover(s, http, NOW, "yt-key")
            assert r.source == "rss" and r.seen == 8
            assert sorted(r.new) == ["vidAAAAAAA1", "vidAAAAAAA2", "vidAAAAAAA6", "vidAAAAAAA7"]
            assert r.skipped == {
                "vidAAAAAAA3": "short",
                "vidAAAAAAA4": "not_crypto",
                "vidAAAAAAA8": "old",
            }
            assert r.deferred == ["vidAAAAAAA5"]  # live: not stored, seen again tomorrow
            v = s.get(McoVideo, "vidAAAAAAA1")
            assert v.priority == 1 and v.duration_s == 723 and v.description == "solid desc"
            assert s.get(McoVideo, "vidAAAAAAA7").priority == 0  # "crypto" names no core coin
            again = disc.discover(s, http, NOW, "yt-key")
            assert again.new == [] and again.skipped == {}
            assert s.scalar(select(func.count()).select_from(McoVideo)) == 7


def test_discover_falls_back_to_the_api_when_rss_fails(seeded) -> None:
    with respx.mock(assert_all_called=False) as mock, httpx.Client() as http:
        mock_youtube(mock, rss_status=404)
        with seeded() as s:
            r = disc.discover(s, http, NOW, "yt-key")
        assert r.source == "api" and r.errors == ["rss:404"] and len(r.new) == 4
        assert mock.routes[1].calls[0].request.url.params["id"] == "UCngIhBkikUe6e7tZTjpKK7Q"
    with respx.mock(assert_all_called=False) as mock, httpx.Client() as http:
        mock.get(RSS).respond(500)
        with seeded() as s:
            r = disc.discover(s, http, NOW, None)  # no key: no fallback
        assert r.source == "none" and r.errors == ["rss:500"]


def test_queue_cap_newest_first_and_degraded(seeded) -> None:
    with respx.mock(assert_all_called=False) as mock, httpx.Client() as http:
        mock_youtube(mock)
        with seeded() as s:
            disc.discover(s, http, NOW, "yt-key")
    with seeded.begin() as s:
        s.add(
            McoVideo(
                video_id="vidDONE0001",
                title="t",
                url="u",
                published_at=NOW,
                status="done",
                processed_at=NOW - dt.timedelta(hours=1),
            )
        )
    with seeded() as s:
        # Cap 4 a day, one already done today; newest first.
        assert disc.queue(s, NOW) == ["vidAAAAAAA1", "vidAAAAAAA2", "vidAAAAAAA7"]
        assert disc.queue(s, NOW, limit=1) == ["vidAAAAAAA1"]
        # Near the cap: 2 a day and core coins only ("Crypto market" is out).
        assert disc.queue(s, NOW, degraded=True) == ["vidAAAAAAA1"]
        assert disc.queue(s, NOW + dt.timedelta(days=1), degraded=True) == [
            "vidAAAAAAA1",
            "vidAAAAAAA2",
        ]


@pytest.mark.parametrize(
    ("iso", "s"),
    [
        ("PT57S", 57),
        ("PT7M35S", 455),
        ("PT1H2M", 3720),
        ("P1DT1S", 86401),
        ("PT0S", 0),
        ("bogus", None),
    ],
)
def test_parse_duration(iso, s) -> None:
    assert disc.parse_duration(iso) == s


def test_keyword_match_is_whole_word() -> None:
    kw = ["sol", "btc", "crypto"]
    assert disc.is_crypto("SOL to the moon", kw) and disc.is_crypto("btc/usd", kw)
    assert not disc.is_crypto("a solid consolidation", kw)


# --- The job ----------------------------------------------------------------------------------


class Notifier:
    def __init__(self) -> None:
        self.alerts = []

    def __call__(self, alert):
        self.alerts.append(alert)
        return {"telegram": "sent", "discord": "sent"}


def run_job(sessions, fake, notifier, **kw):
    with respx.mock(assert_all_called=False) as mock, httpx.Client() as http:
        mock_youtube(mock)
        return mco_daily.run_mco(
            sessions, NOW, gemini=lambda: fake, http=http, notify=notifier, **kw
        )


def labels_reply() -> str:
    lab = [
        {
            "wave_label": "(b)",
            "pivot_kind": "high",
            "approx_date": "2026-08-02",
            "approx_price": 66500,
            "chart_timeframe": "1d",
        },
        {
            "wave_label": "X",
            "pivot_kind": "low",
            "approx_date": "2026-07-03",
            "approx_price": 90000,
            "chart_timeframe": "1d",
        },
    ]
    body = json.loads(good(pivot_labels=lab))
    body["summary"] = f"Summary {CANARY}"
    body["coins"].append({**body["coins"][0], "coin": "XRP"})  # untracked: kept in payload only
    return json.dumps(body)


def test_job_end_to_end(seeded, monkeypatch, caplog, settings_with_keys) -> None:
    caplog.set_level(logging.DEBUG)
    videos = ["vidAAAAAAA1", "vidAAAAAAA2", "vidAAAAAAA7", "vidAAAAAAA6"]
    fake = FakeGemini(
        {
            ("video", "gemini-3.5-flash-lite"): [labels_reply(), good(), good(), "{bad"],
            ("text", "gemini-3.5-flash-lite"): ["{bad again"],
            ("video", "gemini-3.8-flash"): [good(coin="SOL")],
        }
    )
    notifier = Notifier()
    r = run_job(seeded, fake, notifier)
    assert r.status == "success", r.summary()
    assert [v.video_id for v in r.videos] == videos
    first = r.videos[0]
    assert (first.labels, first.matched, first.coins) == (2, 1, 2)
    assert r.videos[3].model == "gemini-3.8-flash"
    with seeded() as s:
        assert {
            v.status for v in s.scalars(select(McoVideo).where(McoVideo.video_id.in_(videos)))
        } == {"done"}
        labels = {lab.label: lab for lab in s.scalars(select(McoWaveLabel))}
        assert {lab.status for lab in labels.values()} == {"pending"}
        assert (
            labels["(b)"].pivot_date == dt.date(2026, 7, 31) and labels["(b)"].pivot_kind == "high"
        )
        assert labels["X"].pivot_date is None and labels["X"].match_note.startswith("unmatched")
        ex = s.scalars(select(McoExtract).where(McoExtract.video_id == "vidAAAAAAA1")).one()
        assert ex.prompt_version == "mco_extract_v1" and CANARY in ex.summary
        assert [c["coin"] for c in ex.payload["coins"]] == ["BTC", "XRP"]
        spend = s.scalars(select(LlmSpend)).all()
        assert len(spend) == 6 and {x.source for x in spend} == {"mco"}
        assert sum(x.cost for x in spend) == 0  # free tier
        run = s.get(JobRun, r.run_id)
        assert run.job == "mco" and run.status == "success" and run.ended_at
    events = [a.event for a in notifier.alerts]
    assert events == ["new_mco_summary"] * 4 + ["mco_review_pending"]
    a = notifier.alerts[0]
    assert a.url == "https://www.youtube.com/watch?v=vidAAAAAAA1" and "BTC bearish" in a.body
    assert (
        "5 new wave labels from 4 video(s) await review (4 unmatched)" in notifier.alerts[-1].body
    )
    # Privacy: no MCO text in the public summary or in any log record.
    summary = r.summary()
    assert CANARY not in summary and "vidAAAAAAA1: done" in summary
    assert "bearish" not in summary and "Bitcoin" not in summary
    assert not [rec for rec in caplog.records if CANARY in rec.getMessage()]


def test_failed_video_and_retry_limit(seeded, settings_with_keys) -> None:
    err = __import__("desk.mco.summarize", fromlist=["GeminiError"]).GeminiError("503")
    fake = FakeGemini(
        {
            (k, m): [err] * 20
            for k in ("video", "text")
            for m in ("gemini-3.5-flash-lite", "gemini-3.8-flash")
        }
    )
    r = run_job(seeded, fake, Notifier(), limit=1)
    assert r.status == "failed" and r.videos[0].error == "gemini-3.8-flash:fallback:503"
    assert "vidAAAAAAA1 failed: gemini-3.8-flash:fallback:503" in r.summary()
    with seeded() as s:
        v = s.get(McoVideo, "vidAAAAAAA1")
        assert (v.status, v.attempts, v.error) == ("failed", 1, "gemini-3.8-flash:fallback:503")
        assert s.get(JobRun, r.run_id).status == "failed"


def test_budget_cap_skips_summaries(seeded, monkeypatch, settings_with_keys) -> None:
    monkeypatch.setattr(
        cost,
        "budget",
        lambda s, today=None: cost.Budget(cost.Decimal(8), cost.Decimal(8), cost.Decimal("6.4")),
    )
    fake = FakeGemini({})
    r = run_job(seeded, fake, Notifier())
    assert r.status == "success" and r.videos == [] and fake.calls == []
    assert "cap reached" in r.notes[0]


def test_switched_off(seeded, monkeypatch) -> None:
    monkeypatch.setattr(mco_daily, "enabled", lambda: False)
    r = mco_daily.run_mco(seeded, NOW, gemini=lambda: FakeGemini({}), notify=Notifier())
    assert r.status == "disabled" and r.run_id is None
    with seeded() as s:
        assert s.scalar(select(func.count()).select_from(JobRun)) == 0


def test_job_writes_nothing_under_the_repo(seeded, monkeypatch, settings_with_keys) -> None:
    real_open = builtins.open
    writes: list[str] = []

    def guarded(file, mode="r", *a, **kw):
        if any(c in mode for c in "wax+") and isinstance(file, str | Path):
            p = Path(file).resolve()
            if p.is_relative_to(REPO_ROOT):
                writes.append(str(p))
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", guarded)
    monkeypatch.setattr(io, "open", guarded)  # pathlib's write_text goes through io.open
    fake = FakeGemini({("video", "gemini-3.5-flash-lite"): [labels_reply()]})
    r = run_job(seeded, fake, Notifier(), limit=1)
    assert r.status == "success" and writes == []


@pytest.fixture
def settings_with_keys(monkeypatch):
    """A YouTube key so discovery asks for durations (the HTTP is mocked)."""
    from pydantic import SecretStr

    real = mco_daily.get_settings()
    fake = real.model_copy(update={"youtube_api_key": SecretStr("yt-key")})
    monkeypatch.setattr(mco_daily, "get_settings", lambda: fake)
