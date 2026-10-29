"""Macro calendar from `config/calendar.yaml` (Stage 1.2).

The YAML is the source of truth (FOMC decisions and US CPI releases, with official URLs).
`sync` makes `calendar_events` match it: new events are inserted, changed times or URLs
updated, and events no longer in the file deleted. Schedules are public well in advance, so the
as-of reader returns the events in a window around `as_of`.
"""

import datetime as dt
from collections.abc import Sequence
from pathlib import Path

import yaml
from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from desk.config import get_settings
from desk.models import CalendarEvent

KINDS = {"fomc", "cpi"}


def load_yaml(path: Path | None = None) -> list[dict]:
    """Validated events: `date`, `time_utc` (time or None), `kind`, `title`, `source_url`."""
    path = path or get_settings().config_dir / "calendar.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    events = []
    for e in cfg.get("events") or []:
        if e["kind"] not in KINDS:
            raise ValueError(f"unknown calendar kind {e['kind']!r} (expected one of {KINDS})")
        day = e["date"] if isinstance(e["date"], dt.date) else dt.date.fromisoformat(e["date"])
        time = dt.time.fromisoformat(e["time_utc"]) if e.get("time_utc") else None
        events.append(
            {"date": day, "time_utc": time, "kind": e["kind"], "title": e["title"],
             "source_url": e.get("source")}
        )  # fmt: skip
    keys = [(e["date"], e["kind"], e["title"]) for e in events]
    if len(keys) != len(set(keys)):
        raise ValueError("calendar.yaml has duplicate (date, kind, title) events")
    return events


def sync(session: Session, path: Path | None = None) -> tuple[int, int]:
    """Make the table match the YAML; returns (events in the file, rows deleted)."""
    events = load_yaml(path)
    keys = [(e["date"], e["kind"], e["title"]) for e in events]
    stale = delete(CalendarEvent)
    if keys:
        stale = stale.where(
            tuple_(CalendarEvent.date, CalendarEvent.kind, CalendarEvent.title).not_in(keys)
        )
    deleted = session.execute(stale).rowcount
    if events:
        stmt = insert(CalendarEvent).values(events)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "kind", "title"],
            set_={"time_utc": stmt.excluded.time_utc, "source_url": stmt.excluded.source_url},
        )
        session.execute(stmt)
    return len(events), deleted


def load_events(
    session: Session,
    as_of: dt.date,
    days_ahead: int = 7,
    days_behind: int = 0,
    kinds: Sequence[str] | None = None,
) -> list[dict]:
    """Events from `as_of - days_behind` to `as_of + days_ahead` (inclusive), soonest first."""
    q = (
        select(CalendarEvent)
        .where(
            CalendarEvent.date >= as_of - dt.timedelta(days=days_behind),
            CalendarEvent.date <= as_of + dt.timedelta(days=days_ahead),
        )
        .order_by(CalendarEvent.date, CalendarEvent.time_utc, CalendarEvent.kind)
    )
    if kinds:
        q = q.where(CalendarEvent.kind.in_(kinds))
    return [
        {"date": e.date, "time_utc": e.time_utc, "kind": e.kind, "title": e.title,
         "source_url": e.source_url}
        for e in session.scalars(q)
    ]  # fmt: skip
