"""MCO video discovery (Section 3.4 step 1, D26, D48).

1. List the channel's newest uploads: the RSS feed first, then the YouTube Data API uploads
   playlist when the feed fails or is empty (it fails from GitHub runners). The API costs
   1 unit per `channels.list`, `playlistItems.list` and `videos.list` call (10,000 a day free).
2. Look up duration and live status for unseen videos (`videos.list`, needs the API key).
3. Store every unseen video once (the primary key dedupes): `new` if it is a finished crypto
   video longer than a Short, published within `mco.backfill_days`; otherwise `skip`.
   Live and upcoming broadcasts are not stored, so they are picked up once they are uploads.
4. `queue` picks what to summarize: newest first, at most `max_videos_per_day` per UTC day
   (videos already processed today count), and near the budget cap (Decision 9 step 2) only
   `mco.degraded_max_videos` videos that name a core coin.

Titles and descriptions are MCO's text: stored in the database only, never logged.
"""

import datetime as dt
import logging
import re
from calendar import timegm
from dataclasses import dataclass, field

import feedparser
import httpx
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from desk.config import get_settings, load_app_settings

log = logging.getLogger(__name__)

RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
API = "https://www.googleapis.com/youtube/v3"
WATCH = "https://www.youtube.com/watch?v={id}"
UA = {"User-Agent": "crypto-desk/1.0 (+https://github.com/robertsolomon002/crypto-desk)"}
CORE = ("BTC", "ETH", "SOL")
MAX_ATTEMPTS = 3  # failed videos are retried on later runs up to this many attempts


@dataclass(frozen=True)
class Candidate:
    video_id: str
    title: str
    description: str
    published_at: dt.datetime


@dataclass(frozen=True)
class Details:
    duration_s: int | None
    live: str  # none | live | upcoming


@dataclass
class DiscoverResult:
    source: str = "none"  # rss | api | none
    seen: int = 0
    new: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)  # video id -> reason
    deferred: list[str] = field(default_factory=list)  # live or upcoming, not stored yet
    errors: list[str] = field(default_factory=list)  # short codes, no MCO text


def mco_config() -> dict:
    """The `mco:` block of `config/feeds.yaml` (channel id, daily cap, keywords)."""
    path = get_settings().config_dir / "feeds.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["mco"]


def pipeline_config() -> dict:
    return load_app_settings().get("mco") or {}


# --- Listing ----------------------------------------------------------------------------------


def _video_id(entry) -> str | None:
    vid = entry.get("yt_videoid")
    if vid:
        return vid
    m = re.search(r"yt:video:([\w-]{11})", entry.get("id", ""))
    return m.group(1) if m else None


def parse_rss(content: bytes) -> list[Candidate]:
    out = []
    for e in feedparser.parse(content).entries:
        vid = _video_id(e)
        stamp = e.get("published_parsed")
        if not vid or not stamp:
            continue
        published = dt.datetime.fromtimestamp(timegm(stamp), dt.UTC)
        desc = e.get("media_description") or e.get("summary") or ""
        out.append(Candidate(vid, e.get("title", ""), desc, published))
    return out


def fetch_rss(client: httpx.Client, channel_id: str) -> list[Candidate]:
    r = client.get(RSS_URL.format(cid=channel_id), headers=UA, follow_redirects=True)
    r.raise_for_status()
    return parse_rss(r.content)


def _api_get(client: httpx.Client, key: str, method: str, **params) -> dict:
    r = client.get(f"{API}/{method}", params={**params, "key": key})
    if r.status_code != 200:  # the body is not logged: Google echoes request details
        raise httpx.HTTPStatusError(
            f"youtube {method} {r.status_code}", request=r.request, response=r
        )
    return r.json()


def fetch_api(client: httpx.Client, key: str, channel_id: str, n: int = 15) -> list[Candidate]:
    """Newest uploads from the channel's uploads playlist (2 quota units)."""
    ch = _api_get(client, key, "channels", part="contentDetails", id=channel_id)
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = _api_get(
        client,
        key,
        "playlistItems",
        part="snippet,contentDetails",
        playlistId=uploads,
        maxResults=n,
    )["items"]
    out = []
    for it in items:
        sn, cd = it["snippet"], it["contentDetails"]
        stamp = cd.get("videoPublishedAt") or sn["publishedAt"]
        published = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        out.append(
            Candidate(cd["videoId"], sn.get("title", ""), sn.get("description", ""), published)
        )
    return out


def parse_duration(iso: str | None) -> int | None:
    """ISO 8601 durations as YouTube writes them: PT#M#S, PT#H#M#S, P#DT#H#M#S."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def fetch_details(client: httpx.Client, key: str, ids: list[str]) -> dict[str, Details]:
    """Duration and live status per video (1 quota unit for up to 50 ids)."""
    if not ids:
        return {}
    items = _api_get(client, key, "videos", part="contentDetails,snippet", id=",".join(ids[:50]))[
        "items"
    ]
    return {
        v["id"]: Details(
            parse_duration(v["contentDetails"].get("duration")),
            v["snippet"].get("liveBroadcastContent", "none"),
        )
        for v in items
    }


# --- Filters ----------------------------------------------------------------------------------


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def is_crypto(text: str, keywords: list[str]) -> bool:
    """Whole-word keyword match, so 'sol' matches 'SOL' but not 'solid'."""
    return bool(_words(text) & {k.lower() for k in keywords})


def names_core_coin(text: str, aliases: dict[str, list[str]]) -> bool:
    words = _words(text)
    return any(words & {a.lower() for a in aliases.get(c, [c])} for c in CORE)


def core_aliases(session: Session) -> dict[str, list[str]]:
    from desk.models import Coin

    rows = session.execute(select(Coin.symbol, Coin.aliases).where(Coin.symbol.in_(CORE)))
    return {s: [s.lower(), *(a or [])] for s, a in rows}


# --- Discover and queue -----------------------------------------------------------------------


def discover(
    session: Session,
    client: httpx.Client,
    now: dt.datetime,
    youtube_key: str | None = None,
) -> DiscoverResult:
    """List uploads, classify unseen ones and store them (see the module docstring)."""
    from desk.models import McoVideo

    cfg, pcfg = mco_config(), pipeline_config()
    result = DiscoverResult()
    candidates: list[Candidate] = []
    try:
        candidates = fetch_rss(client, cfg["channel_id"])
        result.source = "rss"
    except (httpx.HTTPError, ValueError) as exc:
        result.errors.append(f"rss:{_code(exc)}")
    if not candidates and youtube_key:
        try:
            candidates = fetch_api(client, youtube_key, cfg["channel_id"])
            result.source = "api"
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            result.errors.append(f"api:{_code(exc)}")
    if not candidates:
        result.source = "none"
        return result
    result.seen = len(candidates)

    known = set(
        session.scalars(
            select(McoVideo.video_id).where(McoVideo.video_id.in_([c.video_id for c in candidates]))
        )
    )
    unseen = [c for c in candidates if c.video_id not in known]
    details: dict[str, Details] = {}
    if unseen and youtube_key:
        try:
            details = fetch_details(client, youtube_key, [c.video_id for c in unseen])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            result.errors.append(f"details:{_code(exc)}")

    oldest = now - dt.timedelta(days=int(pcfg.get("backfill_days", 3)))
    min_s = int(pcfg.get("min_duration_seconds", 180))
    aliases = core_aliases(session)
    for c in unseen:
        d = details.get(c.video_id)
        if d and d.live in ("live", "upcoming"):
            result.deferred.append(c.video_id)
            continue
        text = f"{c.title} {c.description}"
        reason = None
        if c.published_at < oldest:
            reason = "old"
        elif not is_crypto(text, cfg["crypto_keywords"]):
            reason = "not_crypto"
        elif d and d.duration_s is not None and d.duration_s < min_s:
            reason = "short"
        session.add(
            McoVideo(
                video_id=c.video_id,
                title=c.title,
                description=c.description,
                url=WATCH.format(id=c.video_id),
                published_at=c.published_at,
                status="skip" if reason else "new",
                duration_s=d.duration_s if d else None,
                priority=1 if names_core_coin(text, aliases) else 0,
            )
        )
        if reason:
            result.skipped[c.video_id] = reason
        else:
            result.new.append(c.video_id)
    session.commit()
    log.info(
        "mco discover: source=%s seen=%d new=%d skipped=%d deferred=%d",
        result.source,
        result.seen,
        len(result.new),
        len(result.skipped),
        len(result.deferred),
    )
    return result


def queue(
    session: Session, now: dt.datetime, degraded: bool = False, limit: int | None = None
) -> list[str]:
    """Video ids to summarize now, newest first, within today's cap."""
    from desk.models import McoVideo

    cap = int(mco_config().get("max_videos_per_day", 4))
    if degraded:
        cap = min(cap, int(pipeline_config().get("degraded_max_videos", 2)))
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    done_today = session.scalar(
        select(func.count())
        .select_from(McoVideo)
        .where(McoVideo.processed_at >= day_start, McoVideo.status.in_(("done", "failed")))
    )
    room = max(0, cap - int(done_today or 0))
    if limit is not None:
        room = min(room, limit)
    if room == 0:
        return []
    q = select(McoVideo.video_id).where(
        (McoVideo.status == "new")
        | ((McoVideo.status == "failed") & (McoVideo.attempts < MAX_ATTEMPTS))
    )
    if degraded:
        q = q.where(McoVideo.priority >= 1)
    return list(session.scalars(q.order_by(McoVideo.published_at.desc()).limit(room)))


def _code(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return str(exc.response.status_code)
    return type(exc).__name__
