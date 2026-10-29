"""The generic `series` table: idempotent upserts, last dates and as-of reads (Stage 1.2).

A row `(key, date, value)` is a daily (or monthly) observation. Keys: `fng`, `cm:BTC:CapMVRVCur`,
`fred:DGS10`, `dominance:btc`. As-of rule: a row dated D is known once D has ended (UTC), like a
closed candle, unless the source publishes later; then readers pass a release lag (FRED, D32).
"""

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence

import pandas as pd
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from desk.models import SeriesPoint

UPSERT_BATCH = 1000


def upsert_series(
    session: Session, key: str, points: Iterable[tuple[dt.date, float]], source: str
) -> int:
    """Insert or update points of one series; returns how many were new."""
    rows = [{"key": key, "date": d, "value": v, "source": source} for d, v in points]
    inserted = 0
    for i in range(0, len(rows), UPSERT_BATCH):
        stmt = insert(SeriesPoint).values(rows[i : i + UPSERT_BATCH])
        stmt = stmt.on_conflict_do_update(
            index_elements=["key", "date"],
            set_={"value": stmt.excluded.value, "source": stmt.excluded.source},
        ).returning(literal_column("(xmax = 0)"))
        inserted += sum(1 for (new,) in session.execute(stmt) if new)
    return inserted


def last_date(session: Session, key: str) -> dt.date | None:
    return session.scalar(select(func.max(SeriesPoint.date)).where(SeriesPoint.key == key))


def load_series(
    session: Session,
    keys: Sequence[str],
    as_of: dt.date | None = None,
    start: dt.date | None = None,
    lag_days: Mapping[str, int] | None = None,
) -> pd.DataFrame:
    """Wide frame (one column per key) indexed by UTC midnight, up to `as_of`.

    With `as_of`, a row of key k is included only if `date + lag_days[k] <= as_of`.
    Without `as_of`, everything stored is returned (all of it has been published).
    """
    lag_days = lag_days or {}
    frames: dict[str, pd.Series] = {}
    for key in keys:
        q = select(SeriesPoint.date, SeriesPoint.value).where(SeriesPoint.key == key)
        if as_of is not None:
            q = q.where(SeriesPoint.date <= as_of - dt.timedelta(days=lag_days.get(key, 0)))
        if start is not None:
            q = q.where(SeriesPoint.date >= start)
        rows = session.execute(q.order_by(SeriesPoint.date)).all()
        frames[key] = pd.Series(
            [v for _, v in rows], index=pd.to_datetime([d for d, _ in rows]), dtype="float64"
        )
    df = pd.DataFrame(frames, columns=list(keys))
    df.index = pd.DatetimeIndex(df.index, name="date").tz_localize("UTC")
    return df


def summary(session: Session) -> list[tuple[str, int, dt.date, dt.date]]:
    """(key, rows, first date, last date) for every stored series, for `desk data status`."""
    q = (
        select(
            SeriesPoint.key,
            func.count(),
            func.min(SeriesPoint.date),
            func.max(SeriesPoint.date),
        )
        .group_by(SeriesPoint.key)
        .order_by(SeriesPoint.key)
    )
    return [tuple(r) for r in session.execute(q)]  # type: ignore[misc]
