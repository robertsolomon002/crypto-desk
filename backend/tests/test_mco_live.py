"""Live checks for the MCO sources (RUN_LIVE=1). Output is counts and ids only (Decision 6)."""

import datetime as dt

import httpx
import pytest

from desk.config import get_settings
from desk.mco import discover as disc
from desk.mco import summarize as summ

pytestmark = pytest.mark.live
CHANNEL = "UCngIhBkikUe6e7tZTjpKK7Q"


def test_youtube_listing_live() -> None:
    key = get_settings().youtube_api_key
    with httpx.Client(timeout=30) as http:
        api = disc.fetch_api(http, key.get_secret_value(), CHANNEL) if key else []
        if key:
            assert api and all(len(c.video_id) == 11 for c in api)
            details = disc.fetch_details(http, key.get_secret_value(), [c.video_id for c in api])
            assert all(d.duration_s is not None for d in details.values())
        try:
            rss = disc.fetch_rss(http, CHANNEL)
        except httpx.HTTPError:
            rss = []  # fails from cloud IPs (D26); the API fallback covers it
    assert rss or api


def test_gemini_reads_the_newest_long_video_live() -> None:
    s = get_settings()
    if not (s.google_api_key and s.youtube_api_key):
        pytest.skip("GOOGLE_API_KEY and YOUTUBE_API_KEY needed")
    key = s.youtube_api_key.get_secret_value()
    with httpx.Client(timeout=30) as http:
        cands = disc.fetch_api(http, key, CHANNEL)
        details = disc.fetch_details(http, key, [c.video_id for c in cands])
    video = next(c for c in cands if (details[c.video_id].duration_s or 0) >= 180)
    client = summ.GenaiClient(s.google_api_key.get_secret_value())
    out = summ.summarize(
        client,
        disc.WATCH.format(id=video.video_id),
        video.title,
        video.description,
        video.published_at.date(),
        lambda *a: None,
        models=["gemini-3.5-flash-lite"],
    )
    assert out.extract.summary and isinstance(out.extract.coins, list)
    assert dt.datetime.now(dt.UTC) >= video.published_at
