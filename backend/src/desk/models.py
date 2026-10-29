"""SQLAlchemy 2.0 models for every Section 5 table (Stage 1.1). Later stages only add columns.

All timestamps are timezone-aware UTC. Dates (`date` columns) are UTC calendar days.
"""

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

UTCDateTime = DateTime(timezone=True)


class Base(DeclarativeBase):
    # Deterministic constraint names, so later migrations can refer to them.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def _created_at() -> Mapped[dt.datetime]:
    return mapped_column(UTCDateTime, server_default=func.now())


# --- Market and analytics ---------------------------------------------------------------------


class Coin(Base):
    __tablename__ = "coins"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    source_market: Mapped[str] = mapped_column(String(32))  # ccxt Coinbase symbol, e.g. BTC/USD
    active: Mapped[bool] = mapped_column(server_default="true")
    is_watchlist: Mapped[bool] = mapped_column(server_default="false")
    added_at: Mapped[dt.datetime] = _created_at()


class CandleDaily(Base):
    """Closed daily candles. Coin Metrics backfill rows (D20) are close-only: OHLV are null."""

    __tablename__ = "candles_daily"

    coin: Mapped[str] = mapped_column(ForeignKey("coins.symbol"), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Double)
    high: Mapped[float | None] = mapped_column(Double)
    low: Mapped[float | None] = mapped_column(Double)
    close: Mapped[float] = mapped_column(Double)
    volume: Mapped[float | None] = mapped_column(Double)
    source: Mapped[str] = mapped_column(String(32))  # coinbase | coinmetrics | bitstamp


class Candle4h(Base):
    """4H candles resampled from Coinbase 1h (D22); recent history only. Filled from Stage 3.2."""

    __tablename__ = "candles_4h"

    coin: Mapped[str] = mapped_column(ForeignKey("coins.symbol"), primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(UTCDateTime, primary_key=True)  # bar open time
    open: Mapped[float] = mapped_column(Double)
    high: Mapped[float] = mapped_column(Double)
    low: Mapped[float] = mapped_column(Double)
    close: Mapped[float] = mapped_column(Double)
    volume: Mapped[float] = mapped_column(Double)
    source: Mapped[str] = mapped_column(String(32))


class SeriesPoint(Base):
    """Generic daily series, e.g. `fng`, `fred:DGS10`, `cm:BTC:CapMVRVCur`, `dominance:btc`."""

    __tablename__ = "series"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    value: Mapped[float] = mapped_column(Double)
    source: Mapped[str] = mapped_column(String(32))


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, unique=True)
    published_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, index=True)
    coins: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    fetched_at: Mapped[dt.datetime] = _created_at()


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (UniqueConstraint("date", "kind", "title"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    time_utc: Mapped[dt.time | None]
    kind: Mapped[str] = mapped_column(String(32))  # fomc | cpi | ...
    title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"
    __table_args__ = (UniqueConstraint("key", "params_hash", "as_of"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64))
    params_hash: Mapped[str] = mapped_column(String(64))
    as_of: Mapped[dt.date] = mapped_column(Date)
    data: Mapped[Any] = mapped_column(JSONB)
    computed_at: Mapped[dt.datetime] = _created_at()


# --- Users and agent --------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'member')", name="role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clerk_id: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(16), server_default="member")
    created_at: Mapped[dt.datetime] = _created_at()


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _created_at()


class Message(Base):
    """Chat messages. `cost` is null for user keys (only server-key spend is tracked)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(128))
    tokens_in: Mapped[int | None]
    tokens_out: Mapped[int | None]
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    created_at: Mapped[dt.datetime] = _created_at()


class AgentSnapshot(Base):
    """The exact args and result of one agent tool call (the Data tab's "View data")."""

    __tablename__ = "agent_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    tool: Mapped[str] = mapped_column(String(64))
    args: Mapped[Any] = mapped_column(JSONB)
    result: Mapped[Any] = mapped_column(JSONB)
    as_of: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[dt.datetime] = _created_at()


# --- MCO and views (private, Decision 6) ------------------------------------------------------


class McoVideo(Base):
    __tablename__ = "mco_videos"

    video_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), server_default="new")  # new|done|failed|skip
    low_detail: Mapped[bool] = mapped_column(server_default="false")
    processed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


class McoExtract(Base):
    __tablename__ = "mco_extracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("mco_videos.video_id"), index=True)
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    payload: Mapped[Any] = mapped_column(JSONB)  # the Section 3.4 schema
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _created_at()


class McoWaveLabel(Base):
    """AI-extracted wave labels snapped to pivots. Members see only `approved`/`edited`."""

    __tablename__ = "mco_wave_labels"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'edited')", name="status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    extract_id: Mapped[int] = mapped_column(ForeignKey("mco_extracts.id"), index=True)
    coin: Mapped[str] = mapped_column(ForeignKey("coins.symbol"))
    label: Mapped[str] = mapped_column(String(16))
    timeframe: Mapped[str | None] = mapped_column(String(8))
    approx_date: Mapped[dt.date | None] = mapped_column(Date)
    approx_price: Mapped[float | None] = mapped_column(Double)
    pivot_date: Mapped[dt.date | None] = mapped_column(Date)  # null when unmatched
    pivot_price: Mapped[float | None] = mapped_column(Double)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


class ExternalView(Base):
    __tablename__ = "external_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))  # mco | manual analyst name
    coin: Mapped[str] = mapped_column(ForeignKey("coins.symbol"))
    bias: Mapped[str] = mapped_column(String(16))  # bullish | bearish | neutral
    levels: Mapped[Any | None] = mapped_column(JSONB)
    invalidation: Mapped[float | None] = mapped_column(Double)
    url: Mapped[str | None] = mapped_column(Text)
    extract_id: Mapped[int | None] = mapped_column(ForeignKey("mco_extracts.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = _created_at()


# --- Signals and ops --------------------------------------------------------------------------


class Signal(Base):
    """Append-only, hash-chained (Decision 8). Never updated; definition changes bump `version`."""

    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("version", "week", "coin", "source"),
        CheckConstraint("stance IN ('lean_long', 'flat')", name="stance"),
        CheckConstraint("confidence >= 0.5 AND confidence <= 0.95", name="confidence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int]
    week: Mapped[dt.date] = mapped_column(Date)  # Monday 00:00 UTC of the signal week
    coin: Mapped[str] = mapped_column(ForeignKey("coins.symbol"))
    source: Mapped[str] = mapped_column(String(32))  # desk | coinflip | trend | mco
    stance: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Double)
    entry_low: Mapped[float | None] = mapped_column(Double)
    entry_high: Mapped[float | None] = mapped_column(Double)
    invalidation: Mapped[float | None] = mapped_column(Double)
    target: Mapped[float | None] = mapped_column(Double)
    rationale: Mapped[str | None] = mapped_column(Text)
    transcript_ref: Mapped[str | None] = mapped_column(Text)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = _created_at()


class SignalOutcome(Base):
    __tablename__ = "signal_outcomes"

    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), primary_key=True)
    resolved_at: Mapped[dt.datetime] = _created_at()
    week_close: Mapped[float] = mapped_column(Double)
    direction_hit: Mapped[bool | None]
    first_hit: Mapped[str | None] = mapped_column(String(16))  # target | invalidation | neither
    paper_pnl: Mapped[float | None] = mapped_column(Double)  # after costs
    brier: Mapped[float | None] = mapped_column(Double)


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    week: Mapped[dt.date] = mapped_column(Date, index=True)
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _created_at()


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_job_started", "job", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[dt.datetime] = _created_at()
    ended_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), server_default="running")
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    error: Mapped[str | None] = mapped_column(Text)


class LlmSpend(Base):
    """Server-key spend only (Decision 9). User keys are never recorded."""

    __tablename__ = "llm_spend"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(32))  # chat | desk | brief | mco
    model: Mapped[str] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer)
    tokens_out: Mapped[int] = mapped_column(Integer)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    created_at: Mapped[dt.datetime] = _created_at()
