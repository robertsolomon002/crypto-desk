"""RSS headlines (Stage 1.2): normalize, tag coins, dedupe, strip HTML.

Feeds come from `config/feeds.yaml`. Headlines are untrusted text (Section 3.6): titles are
reduced to plain text (HTML parsed and dropped, entities decoded, control characters removed,
length capped), only http(s) links are kept, and everything goes in through parameterized SQL.
Coins are tagged by whole-word, case-insensitive matches of each coin's aliases in the title
and summary. Duplicates are dropped by canonical URL and by case-folded title.
"""

import datetime as dt
import logging
import re
import unicodedata
from calendar import timegm
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
import yaml
from sqlalchemy import any_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from desk.config import get_settings
from desk.models import News

log = logging.getLogger(__name__)

MAX_TITLE = 300
TRACKING_PREFIXES = ("utm_", "mc_")
TRACKING_PARAMS = {"fbclid", "gclid", "ref", "taid"}


@dataclass(frozen=True)
class Feed:
    name: str
    url: str


@dataclass(frozen=True)
class NewsItem:
    source: str
    title: str
    url: str
    published_at: dt.datetime
    coins: tuple[str, ...]


def load_feeds(path: Path | None = None) -> list[Feed]:
    path = path or get_settings().config_dir / "feeds.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [Feed(f["name"], f["url"]) for f in cfg.get("feeds") or []]


# --- Normalizing ------------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def clean_text(raw: str | None, limit: int = MAX_TITLE) -> str:
    """Plain text: tags dropped, entities decoded, control characters removed, spaces collapsed."""
    if not raw:
        return ""
    parser = _TextExtractor()
    parser.feed(raw)
    parser.close()
    text = "".join(parser.parts)
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\t\n ")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def clean_url(raw: str | None) -> str | None:
    """Canonical http(s) URL without fragment or tracking parameters; None if not http(s)."""
    if not raw:
        return None
    parts = urlsplit(raw.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not (k.lower().startswith(TRACKING_PREFIXES) or k.lower() in TRACKING_PARAMS)
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), "")
    )


def alias_patterns(aliases: Mapping[str, Iterable[str]]) -> dict[str, re.Pattern[str]]:
    """One whole-word, case-insensitive pattern per coin symbol (the symbol counts as an alias)."""
    out = {}
    for symbol, names in aliases.items():
        words = sorted({symbol.lower(), *(n.lower() for n in names)}, key=len, reverse=True)
        alt = "|".join(re.escape(w) for w in words)
        out[symbol] = re.compile(rf"(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9])", re.IGNORECASE)
    return out


def tag_coins(text: str, patterns: Mapping[str, re.Pattern[str]]) -> tuple[str, ...]:
    return tuple(sorted(s for s, p in patterns.items() if p.search(text)))


def _published(entry: Mapping) -> dt.datetime | None:
    # feedparser normalizes dates to UTC struct_time
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return dt.datetime.fromtimestamp(timegm(parsed), tz=dt.UTC)


def parse_feed(
    content: bytes,
    source: str,
    patterns: Mapping[str, re.Pattern[str]],
    now: dt.datetime,
) -> list[NewsItem]:
    """Items with a title, an http(s) link and a date. Future dates are clamped to `now`."""
    parsed = feedparser.parse(content)
    items = []
    for entry in parsed.entries:
        title = clean_text(entry.get("title"))
        url = clean_url(entry.get("link"))
        published = _published(entry)
        if not (title and url and published):
            continue
        summary = clean_text(entry.get("summary"), limit=2000)
        items.append(
            NewsItem(
                source=source,
                title=title,
                url=url,
                published_at=min(published, now),
                coins=tag_coins(f"{title} {summary}", patterns),
            )
        )
    return items


def dedupe(items: Iterable[NewsItem]) -> list[NewsItem]:
    """Keep the earliest item per canonical URL and per case-folded title."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out = []
    for item in sorted(items, key=lambda i: i.published_at):
        title = item.title.casefold()
        if item.url in seen_urls or title in seen_titles:
            continue
        seen_urls.add(item.url)
        seen_titles.add(title)
        out.append(item)
    return out


# --- Fetching and storing ---------------------------------------------------------------------


def fetch_all(
    client: httpx.Client,
    feeds: Sequence[Feed],
    patterns: Mapping[str, re.Pattern[str]],
    now: dt.datetime,
) -> tuple[list[NewsItem], list[str]]:
    """Items from every feed, deduped, plus the names of feeds that failed (others still count)."""
    items: list[NewsItem] = []
    failed: list[str] = []
    for feed in feeds:
        try:
            resp = client.get(feed.url)
            resp.raise_for_status()
            got = parse_feed(resp.content, feed.name, patterns, now)
        except httpx.HTTPError as exc:
            log.warning("feed %s failed: %s", feed.name, type(exc).__name__)
            failed.append(feed.name)
            continue
        if not got:
            failed.append(feed.name)
        items.extend(got)
    return dedupe(items), failed


def store(session: Session, items: Sequence[NewsItem]) -> int:
    """Insert items whose URL and title are not stored yet; returns how many were new."""
    if not items:
        return 0
    titles = [i.title.casefold() for i in items]
    known = {
        t.casefold()
        for t in session.scalars(select(News.title).where(func.lower(News.title).in_(titles)))
    }
    inserted = 0
    for item in items:
        if item.title.casefold() in known:
            continue
        stmt = (
            insert(News)
            .values(
                source=item.source,
                title=item.title,
                url=item.url,
                published_at=item.published_at,
                coins=list(item.coins),
            )
            .on_conflict_do_nothing(index_elements=["url"])
            .returning(News.id)
        )
        inserted += session.execute(stmt).first() is not None
    return inserted


def update(
    session: Session,
    client: httpx.Client,
    aliases: Mapping[str, Iterable[str]],
    now: dt.datetime,
    feeds: Sequence[Feed] | None = None,
) -> tuple[int, list[str]]:
    """Fetch every feed and store new headlines; returns (new rows, failed feed names)."""
    items, failed = fetch_all(client, feeds or load_feeds(), alias_patterns(aliases), now)
    return store(session, items), failed


def load_news(
    session: Session,
    as_of: dt.date | None = None,
    coin: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Newest headlines published by the end of `as_of` (UTC), optionally for one coin."""
    q = select(News).order_by(News.published_at.desc(), News.id.desc()).limit(limit)
    if as_of is not None:
        end = dt.datetime.combine(as_of + dt.timedelta(days=1), dt.time(), tzinfo=dt.UTC)
        q = q.where(News.published_at < end)
    if coin is not None:
        q = q.where(any_(News.coins) == coin.upper())
    return [
        {"source": n.source, "title": n.title, "url": n.url, "published_at": n.published_at,
         "coins": list(n.coins)}
        for n in session.scalars(q)
    ]  # fmt: skip
