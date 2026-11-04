"""Append-only, hash-chained `signals` rows (Decision 8, Section 3.5).

Each row's `hash` is SHA-256 over its canonical content plus the previous row's hash (by id),
so editing or removing any row breaks every later hash (`verify`). The chain is global across
coins, sources and versions. Writers take a transaction-scoped advisory lock, so two jobs can't
fork the chain. The database trigger from migration 0003 refuses UPDATE and DELETE.
"""

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from desk.models import Signal

Stance = Literal["lean_long", "flat"]
Source = Literal["desk", "coinflip", "trend", "mco"]
SOURCES: tuple[Source, ...] = ("desk", "coinflip", "trend", "mco")
LOCK_KEY = 7_100_001  # pg_advisory_xact_lock key for chain writers
HASHED = (
    "version",
    "week",
    "coin",
    "source",
    "stance",
    "confidence",
    "entry_low",
    "entry_high",
    "invalidation",
    "target",
    "rationale",
    "transcript_ref",
)


@dataclass(frozen=True)
class Proposed:
    """A signal before it is written."""

    coin: str
    source: Source
    stance: Stance
    confidence: float
    entry_low: float | None = None
    entry_high: float | None = None
    invalidation: float | None = None
    target: float | None = None
    rationale: str | None = None
    transcript_ref: str | None = None

    def p_up(self) -> float:
        """The probability of a higher close the stance implies: `confidence` for lean_long,
        1 - `confidence` for flat (D51)."""
        return self.confidence if self.stance == "lean_long" else 1 - self.confidence


def version_number(label: str | int) -> int:
    """`v1` (settings.yaml) -> 1 (the `signals.version` column)."""
    if isinstance(label, int):
        return label
    return int(str(label).lower().removeprefix("v"))


def content(row: Signal | dict[str, Any]) -> dict[str, Any]:
    get = row.get if isinstance(row, dict) else lambda k: getattr(row, k)
    out = {k: get(k) for k in HASHED}
    week = out["week"]
    out["week"] = week.isoformat() if isinstance(week, dt.date) else week
    for k in ("confidence", "entry_low", "entry_high", "invalidation", "target"):
        if out[k] is not None:
            out[k] = float(out[k])
    return out


def row_hash(fields: dict[str, Any], prev_hash: str | None) -> str:
    body = json.dumps(
        {**fields, "prev_hash": prev_hash},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def last_hash(session: Session) -> str | None:
    return session.scalar(select(Signal.hash).order_by(Signal.id.desc()).limit(1))


def append(session: Session, version: int, week: dt.date, signals: list[Proposed]) -> list[Signal]:
    """Write `signals` in order, each chained to the one before. Skips (coin, source) pairs that
    already have a row for this version and week, so a re-run fills gaps only. Flushes; the
    caller commits."""
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
    q = select(Signal.coin, Signal.source).where(Signal.version == version, Signal.week == week)
    existing = {(coin, source) for coin, source in session.execute(q)}
    prev = last_hash(session)
    rows: list[Signal] = []
    for p in signals:
        if (p.coin, p.source) in existing:
            continue
        fields = content({"version": version, "week": week, **asdict(p)})
        h = row_hash(fields, prev)
        row = Signal(version=version, week=week, prev_hash=prev, hash=h, **asdict(p))
        session.add(row)
        session.flush()
        rows.append(row)
        existing.add((p.coin, p.source))
        prev = h
    return rows


def verify(session: Session) -> list[str]:
    """Every break in the chain (empty when intact)."""
    problems = []
    prev: str | None = None
    for row in session.scalars(select(Signal).order_by(Signal.id)):
        if row.prev_hash != prev:
            problems.append(f"signal {row.id}: prev_hash doesn't match the row before")
        if row_hash(content(row), row.prev_hash) != row.hash:
            problems.append(f"signal {row.id}: hash doesn't match its content")
        prev = row.hash
    return problems
