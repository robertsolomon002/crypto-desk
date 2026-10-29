"""Daily OHLCV from Coinbase via ccxt, weekly resampling, validation (Stage 1.1).

- Coinbase (`ccxt` id `coinbase`) is canonical. BTC before Coinbase's first day comes from
  Coin Metrics `PriceUSD`, close only, stored with `source="coinmetrics"` (D20).
- Only closed candles are stored: a daily bar is kept once its day has fully ended in UTC.
- Updates are incremental and idempotent: refetch from (last stored day - 3 days) and upsert.
- Weekly bars are resampled on the fly, weeks running Monday 00:00 UTC to the next Monday.
"""

import datetime as dt
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import ccxt
import httpx
import pandas as pd
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from desk.data import coinmetrics
from desk.models import CandleDaily, Coin

log = logging.getLogger(__name__)

DAY_MS = 86_400_000
WINDOW = 300  # Coinbase returns at most 300 candles per request (ccxt coinbase.fetch_ohlcv)
HISTORY_START = dt.date(2010, 1, 1)  # walk forward from here when a coin has no rows yet
OVERLAP_DAYS = 3
RETRIES = 3
BIG_MOVE = 0.40
UPSERT_BATCH = 1000

# Coins whose pre-Coinbase history is backfilled from Coin Metrics `PriceUSD` (D20).
CM_BACKFILL = {"BTC": "btc"}

OHLCV = ["open", "high", "low", "close", "volume"]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def make_exchange() -> ccxt.Exchange:
    return ccxt.coinbase({"enableRateLimit": True})


def _to_ms(day: dt.date) -> int:
    return int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.UTC).timestamp() * 1000)


def _to_date(ms: int) -> dt.date:
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.UTC).date()


def _with_retries[T](fn: Callable[[], T], sleep: Callable[[float], None] = time.sleep) -> T:
    for attempt in range(1, RETRIES + 1):
        try:
            return fn()
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as exc:
            if attempt == RETRIES:
                raise
            log.warning("ccxt attempt %d failed (%s); retrying", attempt, type(exc).__name__)
            sleep(2.0**attempt)
    raise AssertionError("unreachable")


def fetch_daily(
    exchange: ccxt.Exchange,
    symbol: str,
    since: dt.date,
    now: dt.datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[list[float]]:
    """Closed daily candles `[ms, o, h, l, c, v]` from `since` (inclusive) to the last closed day.

    Pages forward in 300-day windows. Empty windows (before a market existed) are skipped.
    """
    now_ms = int((now or utc_now()).timestamp() * 1000)
    start = _to_ms(since)
    out: dict[int, list[float]] = {}
    while start + DAY_MS <= now_ms:
        candles = _with_retries(
            lambda s=start: exchange.fetch_ohlcv(symbol, "1d", since=s, limit=WINDOW), sleep
        )
        end = start + WINDOW * DAY_MS
        for c in candles:
            if start <= c[0] < end and c[0] + DAY_MS <= now_ms:
                out[int(c[0])] = c
        start = end
    return [out[k] for k in sorted(out)]


# --- Database ---------------------------------------------------------------------------------


def upsert_candles(session: Session, rows: Sequence[dict]) -> int:
    """Insert or update `candles_daily` rows; returns how many were new."""
    inserted = 0
    for i in range(0, len(rows), UPSERT_BATCH):
        stmt = insert(CandleDaily).values(list(rows[i : i + UPSERT_BATCH]))
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin", "date"],
            set_={c: stmt.excluded[c] for c in [*OHLCV, "source"]},
        ).returning(literal_column("(xmax = 0)"))
        inserted += sum(1 for (new,) in session.execute(stmt) if new)
    return inserted


def _bound(session: Session, coin: str, source: str, agg: Callable) -> dt.date | None:
    return session.scalar(
        select(agg(CandleDaily.date)).where(CandleDaily.coin == coin, CandleDaily.source == source)
    )


def update_coin(
    session: Session,
    coin: Coin,
    exchange: ccxt.Exchange,
    cm_client: httpx.Client | None = None,
    now: dt.datetime | None = None,
) -> dict[str, int]:
    """Fetch new closed candles for one coin, plus the one-time BTC backfill.

    Returns the number of new rows per source.
    """
    added: dict[str, int] = {}
    last = _bound(session, coin.symbol, "coinbase", func.max)
    since = last - dt.timedelta(days=OVERLAP_DAYS) if last else HISTORY_START
    candles = fetch_daily(exchange, coin.source_market, since, now)
    rows = [
        {"coin": coin.symbol, "date": _to_date(ms), "open": o, "high": h, "low": lo,
         "close": c, "volume": v, "source": "coinbase"}
        for ms, o, h, lo, c, v in candles
    ]  # fmt: skip
    added["coinbase"] = upsert_candles(session, rows)

    asset = CM_BACKFILL.get(coin.symbol)
    first = _bound(session, coin.symbol, "coinbase", func.min)
    if asset and first and cm_client and not _bound(session, coin.symbol, "coinmetrics", func.max):
        points = coinmetrics.fetch_asset_metric(
            cm_client, asset, "PriceUSD", HISTORY_START, first - dt.timedelta(days=1)
        )
        cm_rows = [
            {"coin": coin.symbol, "date": d, "open": None, "high": None, "low": None,
             "close": p, "volume": None, "source": "coinmetrics"}
            for d, p in points
            if d < first
        ]  # fmt: skip
        added["coinmetrics"] = upsert_candles(session, cm_rows)
    return added


def load_daily(session: Session, coin: str, as_of: dt.date | None = None) -> pd.DataFrame:
    """Daily candles for `coin` up to and including `as_of`, indexed by UTC midnight."""
    q = select(CandleDaily).where(CandleDaily.coin == coin).order_by(CandleDaily.date)
    if as_of is not None:
        q = q.where(CandleDaily.date <= as_of)
    records = [
        {"date": r.date, **{c: getattr(r, c) for c in OHLCV}, "source": r.source}
        for r in session.scalars(q)
    ]
    return to_frame(records)


def to_frame(records: Sequence[dict]) -> pd.DataFrame:
    df = pd.DataFrame(records, columns=["date", *OHLCV, "source"])
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("date")), name="date").tz_localize("UTC")
    return df.astype({c: "float64" for c in OHLCV})


# --- Resampling and validation ----------------------------------------------------------------


def resample_weekly(daily: pd.DataFrame, include_partial: bool = False) -> pd.DataFrame:
    """Weekly OHLCV, weeks Monday 00:00 UTC to next Monday, labeled by the Monday.

    Close-only days (Coin Metrics) contribute their close as open, high and low.
    Without `include_partial`, weeks not fully covered by the data (at either end) are dropped.
    """
    if daily.empty:
        return pd.DataFrame(columns=OHLCV, index=pd.DatetimeIndex([], tz="UTC", name="week"))
    d = daily[OHLCV].copy()
    for col in ("open", "high", "low"):
        d[col] = d[col].fillna(d["close"])
    weekly = d.resample("W-MON", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    weekly = weekly.dropna(subset=["close"])
    if not include_partial:
        first, last = daily.index.min(), daily.index.max()
        week = pd.Timedelta(days=7)
        keep = (weekly.index >= first) & (weekly.index + week <= last + pd.Timedelta(days=1))
        weekly = weekly[keep]
    weekly.index.name = "week"
    return weekly


@dataclass(frozen=True)
class Issue:
    kind: str  # gap | duplicate | ohlc | big_move
    date: dt.date
    detail: str


def validate(daily: pd.DataFrame) -> list[Issue]:
    """Gaps, duplicate days, OHLC inconsistencies and close-to-close moves over 40%."""
    issues: list[Issue] = []
    idx = daily.index
    for ts in idx[idx.duplicated()].unique():
        issues.append(Issue("duplicate", ts.date(), "date appears more than once"))
    d = daily[~idx.duplicated(keep="last")].sort_index()

    days = d.index.to_series().diff().dt.days
    for ts, n in days[days > 1].items():
        start = (ts - pd.Timedelta(days=int(n) - 1)).date()
        issues.append(Issue("gap", start, f"{int(n) - 1} missing day(s) before {ts.date()}"))

    full = d.dropna(subset=["open", "high", "low"])
    bad = (
        (full[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (full["low"] > full[["open", "close"]].min(axis=1))
        | (full["high"] < full[["open", "close"]].max(axis=1))
    )
    for ts, row in full[bad].iterrows():
        o, h, lo, c = row["open"], row["high"], row["low"], row["close"]
        issues.append(Issue("ohlc", ts.date(), f"o={o} h={h} l={lo} c={c}"))
    for ts in d.index[d["close"] <= 0]:
        if ts not in full.index:
            issues.append(Issue("ohlc", ts.date(), "close <= 0"))

    ret = d["close"].pct_change()
    for ts, r in ret[ret.abs() > BIG_MOVE].items():
        issues.append(Issue("big_move", ts.date(), f"close-to-close {r:+.1%}"))
    return sorted(issues, key=lambda i: (i.date, i.kind))
